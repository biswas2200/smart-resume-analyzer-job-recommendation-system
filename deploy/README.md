# Deploying the beta

The whole stack runs on one Compute Engine VM with Docker Compose
(`docker-compose.yml` here). Caddy is the only public entry point: it serves
HTTPS for a free `sslip.io` name and passes everything to the frontend's
nginx, which proxies `/api/` to the backend. Postgres, MinIO, the backend and
the ML service are not reachable from outside.

Decided 22 Oct 2026 for the 23 Oct demo: `e2-standard-2` (2 vCPU, 8 GB) in
`asia-south1-a`, about ₹7 an hour while running. Stop it when not needed; the
disk (30 GB, about ₹100 a month) keeps the data.

## One-time setup (laptop, gcloud)

```bash
PROJECT=smart-resume-analyzer-a7x2
BUCKET=smart-resume-analyzer-a7x2-data
SA=smart-resume-analyser-app@$PROJECT.iam.gserviceaccount.com

# A service account for the app: Gemini on Vertex AI, and read access to the
# trained models in the bucket only (runs/), never the resumes in it.
gcloud iam service-accounts create smart-resume-analyser-app --display-name="Smart Resume Analyser and Job Recommendation System beta app"
gcloud projects add-iam-policy-binding $PROJECT --member=serviceAccount:$SA \
  --role=roles/aiplatform.user --condition=None
gcloud storage buckets add-iam-policy-binding gs://$BUCKET --member=serviceAccount:$SA \
  --role=roles/storage.objectViewer \
  --condition="title=models-only,expression=resource.name.startsWith(\"projects/_/buckets/$BUCKET/objects/runs/\")"
# Listing objects is checked on the bucket, not an object, so it needs its own grant.
gcloud storage buckets add-iam-policy-binding gs://$BUCKET --member=serviceAccount:$SA \
  --role=roles/storage.legacyBucketReader

gcloud compute instances create smart-resume-analyser-beta --zone=asia-south1-a \
  --machine-type=e2-standard-2 --image-family=ubuntu-2404-lts-amd64 --image-project=ubuntu-os-cloud \
  --boot-disk-size=30GB --service-account=$SA --scopes=cloud-platform \
  --tags=http-server,https-server
gcloud compute firewall-rules create allow-http-https --allow=tcp:80,tcp:443 \
  --target-tags=http-server,https-server   # once per project
```

## Deploy (on the VM)

Docker Hub no longer serves MinIO's images, so copy the one the local stack
uses (laptop, once per VM):

```bash
docker tag minio/minio:latest smart-resume-analyser-job-recommendation-system/minio:RELEASE.2025-09-07T16-13-09Z
docker save smart-resume-analyser-job-recommendation-system/minio:RELEASE.2025-09-07T16-13-09Z | gzip > minio.tar.gz
gcloud compute scp minio.tar.gz smart-resume-analyser-beta:~/ --zone=asia-south1-a
gcloud compute ssh smart-resume-analyser-beta --zone=asia-south1-a --command='gunzip -c minio.tar.gz | sudo docker load'
```

Then on the VM:

```bash
gcloud compute ssh smart-resume-analyser-beta --zone=asia-south1-a
git clone -b BRANCH https://github.com/biswas2200/smart-resume-analyzer-job-recommendation-system.git smart-resume-analyser-job-recommendation-system
cd smart-resume-analyser-job-recommendation-system
bash deploy/setup.sh docker
bash deploy/setup.sh env ADMIN_EMAIL   # writes deploy/.env with fresh secrets
bash deploy/setup.sh up
```

The first start downloads the NER model from the bucket (about a minute)
before the ML service answers. The site is then at
`https://<ip-with-dashes>.sslip.io` (see `SITE_ADDRESS` in `deploy/.env`).

Update: `git pull && bash deploy/setup.sh up`. Logs:
`cd deploy && sudo docker compose logs -f backend`.

## Job data

A new database has no companies or jobs. Sign in with the admin email, then
call `POST /api/admin/jobs/import-startup-map` (about 20 minutes, one page a
second) or load a dump of `companies` and `job_postings`, then
`POST /api/admin/jobs/refresh` and `POST /api/admin/jobs/market-demand`. The
daily refresh at 06:30 India time keeps it current.

## Stop paying

```bash
gcloud compute instances stop smart-resume-analyser-beta --zone=asia-south1-a    # keeps the disk and data
gcloud compute instances delete smart-resume-analyser-beta --zone=asia-south1-a  # removes everything
```

A stopped VM gets a new IP when started again (no static IP is reserved), so
`SITE_ADDRESS` in `deploy/.env` must be updated (delete `.env` and run
`setup.sh env` again only if the data can be lost, since the secrets protect it).
