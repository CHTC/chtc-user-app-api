from httpx import Client

from userapp.api.tests.fake_data import project_data_f

LOOKUP_ROUTES = ["/fields_of_science", "/college_and_departments"]


class TestReferenceLookups:
    """The two read-only reference tables seeded by the rich-projects migration."""

    def test_lookups_require_authentication(self, api_client: Client):
        """Neither lookup is public, even though both are read-only."""

        for route in LOOKUP_ROUTES:
            response = api_client.get(route)
            assert response.status_code == 401, (
                f"Unauthenticated GET {route} should return 401, got {response.status_code}: {response.text}"
            )

    def test_lookups_return_the_whole_table_by_default(self, existing_admin_client: Client):
        """The default page_size covers the seeded data, so a picker gets every row in one request."""

        for route in LOOKUP_ROUTES:
            response = existing_admin_client.get(route)
            assert response.status_code == 200, f"GET {route} should return 200, got {response.text}"

            total = int(response.headers["X-Total-Count"])
            assert len(response.json()) == total, (
                f"GET {route} returned {len(response.json())} of {total} rows - the default page_size truncates the table"
            )

    def test_seeded_reference_data_is_present(self, existing_admin_client: Client):
        """Both tables are seeded by the migration, not empty in test."""

        fos = existing_admin_client.get("/fields_of_science").json()
        assert len(fos) > 1000, f"fields_of_science should be seeded from the NSF table, got {len(fos)} rows"
        assert len({row['fos_id'] for row in fos}) == len(fos), "fos_id is the primary key and must be unique"

        departments = existing_admin_client.get("/college_and_departments").json()
        assert len(departments) > 100, f"college_and_departments should be seeded, got {len(departments)} rows"

        pairs = [(row['college'], row['department']) for row in departments]
        assert len(set(pairs)) == len(pairs), (
            "(college, department) is the natural key and is uniquely constrained, so the lookup must not repeat a pair"
        )

    def test_paging_a_lookup_is_ordered_and_complete(self, existing_admin_client: Client):
        """Paging relies on a deterministic ORDER BY, so no row is repeated or skipped."""

        collected = []
        for page in range(20):
            response = existing_admin_client.get(f"/fields_of_science?page={page}&page_size=100")
            assert response.status_code == 200, f"Paging /fields_of_science should return 200, got {response.text}"

            rows = response.json()
            if not rows:
                break

            ids = [row['fos_id'] for row in rows]
            assert ids == sorted(ids), f"Page {page} of /fields_of_science came back unordered"
            collected.extend(ids)

        total = int(existing_admin_client.get("/fields_of_science").headers["X-Total-Count"])
        assert len(collected) == total, f"Paging collected {len(collected)} rows but the table holds {total}"
        assert len(set(collected)) == total, "Paging repeated at least one row"

    def test_filtering_a_lookup(self, existing_admin_client: Client):
        """The lookups go through the shared query parser, so filters still apply."""

        all_rows = existing_admin_client.get("/fields_of_science").json()
        target = all_rows[0]

        response = existing_admin_client.get(f"/fields_of_science?fos_id=eq.{target['fos_id']}")
        assert response.status_code == 200, f"Filtering /fields_of_science should return 200, got {response.text}"
        assert [row['fos_id'] for row in response.json()] == [target['fos_id']], (
            f"Filtering on fos_id should return only that row, got {response.text}"
        )


class TestProjectReferenceRelationships:
    """A project's college/department and field of science come back embedded, not just as ids."""

    def _reference_rows(self, admin_client: Client) -> tuple[dict, dict]:
        department = admin_client.get("/college_and_departments").json()[0]
        field_of_science = admin_client.get("/fields_of_science").json()[0]
        return department, field_of_science

    def test_project_embeds_its_reference_rows(self, existing_admin_client: Client):
        """The relationships are lazy="select", so this fails loudly if the load options go missing."""

        department, field_of_science = self._reference_rows(existing_admin_client)

        create_response = existing_admin_client.post(
            "/projects",
            json=project_data_f(
                college_and_department_id=department['id'],
                fos_id=field_of_science['fos_id'],
            ),
        )
        assert create_response.status_code == 201, (
            f"POST /projects should return 201, got {create_response.status_code}: {create_response.text}"
        )
        project = create_response.json()

        try:
            assert project['college_and_department'] == department, (
                f"POST /projects should embed the college/department row, got {project.get('college_and_department')}"
            )
            assert project['field_of_science'] == field_of_science, (
                f"POST /projects should embed the field of science row, got {project.get('field_of_science')}"
            )

            get_response = existing_admin_client.get(f"/projects/{project['id']}")
            assert get_response.status_code == 200, f"GET /projects/{project['id']} should return 200, got {get_response.text}"
            assert get_response.json()['college_and_department'] == department, "GET one should embed the college/department row"
            assert get_response.json()['field_of_science'] == field_of_science, "GET one should embed the field of science row"

            list_response = existing_admin_client.get(f"/projects?id=eq.{project['id']}")
            assert list_response.status_code == 200, f"GET /projects should return 200, got {list_response.text}"
            assert list_response.json()[0]['college_and_department'] == department, "The list endpoint should embed the college/department row"
            assert list_response.json()[0]['field_of_science'] == field_of_science, "The list endpoint should embed the field of science row"
        finally:
            existing_admin_client.delete(f"/projects/{project['id']}")

    def test_clearing_the_reference_ids_clears_the_embedded_rows(self, existing_admin_client: Client):
        """Setting either id back to null has to drop the embedded object too."""

        department, field_of_science = self._reference_rows(existing_admin_client)

        create_response = existing_admin_client.post(
            "/projects",
            json=project_data_f(
                college_and_department_id=department['id'],
                fos_id=field_of_science['fos_id'],
            ),
        )
        assert create_response.status_code == 201, f"POST /projects should return 201, got {create_response.text}"
        project = create_response.json()

        try:
            update_response = existing_admin_client.put(
                f"/projects/{project['id']}",
                json={"college_and_department_id": None, "fos_id": None},
            )
            assert update_response.status_code == 200, (
                f"PUT /projects/{project['id']} should return 200, got {update_response.status_code}: {update_response.text}"
            )
            assert update_response.json()['college_and_department'] is None, "Clearing the id should clear the embedded college/department"
            assert update_response.json()['field_of_science'] is None, "Clearing the id should clear the embedded field of science"
        finally:
            existing_admin_client.delete(f"/projects/{project['id']}")

    def test_unknown_reference_ids_are_rejected(self, existing_admin_client: Client):
        """Both columns are foreign keys, so a bad value is a 400 rather than a silent write."""

        response = existing_admin_client.post("/projects", json=project_data_f(fos_id="99.9999"))
        assert response.status_code == 400, (
            f"POST /projects with an unknown fos_id should return 400, got {response.status_code}: {response.text}"
        )

        response = existing_admin_client.post("/projects", json=project_data_f(college_and_department_id=10 ** 8))
        assert response.status_code == 400, (
            f"POST /projects with an unknown college_and_department_id should return 400, got {response.status_code}: {response.text}"
        )


class TestProjectDisplayName:
    """display_name has to reach the project lists the UI actually reads, not just /projects."""

    def test_display_name_on_the_project_endpoints(self, existing_admin_client: Client):
        payload = project_data_f(display_name="A Readable Project Name")

        create_response = existing_admin_client.post("/projects", json=payload)
        assert create_response.status_code == 201, f"POST /projects should return 201, got {create_response.text}"
        project = create_response.json()

        try:
            assert project['display_name'] == payload['display_name'], "POST /projects should echo display_name"

            get_response = existing_admin_client.get(f"/projects/{project['id']}")
            assert get_response.json()['display_name'] == payload['display_name'], "GET one should return display_name"
        finally:
            existing_admin_client.delete(f"/projects/{project['id']}")

    def test_a_project_created_without_a_display_name_defaults_to_its_name(self, existing_admin_client: Client):
        """trg_default_project_display_name fills it in server-side on insert."""

        payload = project_data_f()
        del payload['display_name']

        create_response = existing_admin_client.post("/projects", json=payload)
        assert create_response.status_code == 201, f"POST /projects should return 201, got {create_response.text}"
        project = create_response.json()

        try:
            assert project['display_name'] == payload['name'], (
                f"An omitted display_name should default to name, got {project['display_name']!r}"
            )

            get_response = existing_admin_client.get(f"/projects/{project['id']}")
            assert get_response.json()['display_name'] == payload['name'], (
                "The default should be persisted, not just present on the create response"
            )
        finally:
            existing_admin_client.delete(f"/projects/{project['id']}")

    def test_an_explicit_null_display_name_still_defaults_to_name(self, existing_admin_client: Client):
        """The ORM always sends the column, so the insert carries an explicit null - the
        trigger has to treat that the same as omitting it."""

        payload = project_data_f()
        payload['display_name'] = None

        create_response = existing_admin_client.post("/projects", json=payload)
        assert create_response.status_code == 201, f"POST /projects should return 201, got {create_response.text}"
        project = create_response.json()

        try:
            assert project['display_name'] == payload['name'], (
                f"An explicitly null display_name should default to name, got {project['display_name']!r}"
            )
        finally:
            existing_admin_client.delete(f"/projects/{project['id']}")

    def test_display_name_on_a_users_project_list(self, existing_admin_client: Client, filled_out_project: dict):
        """/users/{id}/projects is backed by the joined_projects view, which has to carry it."""

        user = filled_out_project['users'][0]

        response = existing_admin_client.get(f"/users/{user['id']}/projects")
        assert response.status_code == 200, (
            f"GET /users/{user['id']}/projects should return 200, got {response.status_code}: {response.text}"
        )

        entry = next(
            (row for row in response.json() if row['project_id'] == filled_out_project['id']),
            None,
        )
        assert entry is not None, f"The user's project list should include project {filled_out_project['id']}"
        assert entry['project_display_name'] == filled_out_project['display_name'], (
            f"The user's project list should carry project_display_name, got {entry.get('project_display_name')}"
        )

    def test_display_name_on_the_user_record(self, existing_admin_client: Client, filled_out_project: dict):
        """UserGetFull.projects embeds the same view, so /users/{id} has to carry it too."""

        user = filled_out_project['users'][0]

        response = existing_admin_client.get(f"/users/{user['id']}")
        assert response.status_code == 200, f"GET /users/{user['id']} should return 200, got {response.text}"

        entry = next(
            (row for row in response.json()['projects'] if row['project_id'] == filled_out_project['id']),
            None,
        )
        assert entry is not None, f"The user record should include project {filled_out_project['id']}"
        assert entry['project_display_name'] == filled_out_project['display_name'], (
            f"The user record's project list should carry project_display_name, got {entry.get('project_display_name')}"
        )
