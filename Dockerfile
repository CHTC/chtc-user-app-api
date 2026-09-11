# Debian rather than Alpine: HTCondor publishes no musl packages, and the job
# history endpoints shell out to condor_q (userapp/api/util/htcondor_cli.py).
# Pinned to bookworm because the apt repository below is per-release.
FROM python:3.12-slim-bookworm

EXPOSE 8000

# Set the working directory
WORKDIR /app

# HTCondor command-line tools. Only condor_q is used, but there is no
# tools-only package; `condor` installs the daemons too, and nothing starts
# them. HTCONDOR_SERIES picks the repository: an LTS series such as 25.0, or a
# feature series such as 25.x. Debian packages exist for amd64 only, so build
# with --platform linux/amd64 (as the README already does).
ARG HTCONDOR_SERIES=25.0
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl \
 && install -d -m 0755 /etc/apt/keyrings \
 && curl -fsSL "https://research.cs.wisc.edu/htcondor/repo/keys/HTCondor-${HTCONDOR_SERIES}-Key" \
      -o /etc/apt/keyrings/htcondor.asc \
 && echo "deb [signed-by=/etc/apt/keyrings/htcondor.asc] https://htcss-downloads.chtc.wisc.edu/repo/debian/${HTCONDOR_SERIES} bookworm main" \
      > /etc/apt/sources.list.d/htcondor.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends condor \
 && apt-get purge -y --auto-remove curl \
 && rm -rf /var/lib/apt/lists/* \
 && condor_q -version

COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY userapp ./userapp
COPY alembic.ini alembic.ini
COPY alembic ./alembic

ENV PYTHON_ENV=production

CMD ["uvicorn", "userapp.main:create_app", "--host", "0.0.0.0", "--proxy-headers", "--forwarded-allow-ips", "*", "--factory"]
