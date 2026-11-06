class TestPiProjects:

    def test_requires_staff(self, nonadmin_client):
        assert nonadmin_client.get("/pi-projects").status_code == 403

    def test_lists_every_effective_member_of_a_pi_group(self, existing_admin_client, project, group, plain_user_factory):
        direct, nested = plain_user_factory(0), plain_user_factory(1)
        existing_admin_client.post(f"/projects/{project['id']}/pis", json={"user_id": direct['id']})
        existing_admin_client.post(f"/groups/{group['id']}/members", json={"user_id": nested['id']})
        existing_admin_client.post(f"/groups/{project['pi_group_id']}/members", json={"group_id": group['id']})

        response = existing_admin_client.get("/pi-projects", params={"project_id": f"eq.{project['id']}"})
        assert response.status_code == 200, response.text
        rows = response.json()
        assert {r['user_id'] for r in rows} == {direct['id'], nested['id']}, "PIs reached through a nested group count"
        for row in rows:
            assert row['project_name'] == project['name'] and row['project_display_name'] == project['display_name']
            assert row['name'] and row['email1']

    def test_project_members_who_are_not_pis_are_not_listed(self, existing_admin_client, project, plain_user_factory):
        member = plain_user_factory(0)
        existing_admin_client.post(f"/projects/{project['id']}/users", json={"user_id": member['id']})

        assert existing_admin_client.get("/pi-projects", params={"project_id": f"eq.{project['id']}"}).json() == []

    def test_removing_a_pi_removes_the_row(self, existing_admin_client, project, plain_user_factory):
        pi = plain_user_factory(0)
        existing_admin_client.post(f"/projects/{project['id']}/pis", json={"user_id": pi['id']})
        existing_admin_client.delete(f"/projects/{project['id']}/pis/{pi['id']}")

        assert existing_admin_client.get("/pi-projects", params={"project_id": f"eq.{project['id']}"}).json() == []
