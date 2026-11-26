# Deploying legal.folonto.com

The Oracle ARM VM also hosts the Defter stack. Legal Assistant uses its own Compose project,
Postgres volume, Cloudflare Tunnel and S3 bucket. The only Legal port mapped on the VM is
`127.0.0.1:3100`. Cloudflare forwards `legal.folonto.com` to that port over the tunnel.
The proxy redirects HTTP to HTTPS. Postgres and the API are reachable within the Compose network.

## Configure and release

Place the checkout at `/opt/legal-folonto` with Docker and Docker Compose installed. Copy
`deploy/.env.example` to `deploy/.env` with mode 600. Set a random hex Postgres password,
an independent random session secret, and an independent 32-byte URL-safe base64 document
encryption key. Save a recovery copy of the encryption key separately. Use a strong private
`INVITE_CODE` to enroll users. Clearing it and recreating the API closes registration.

Enable S3 Block Public Access for the bucket. Give the API identity permission to get, put
and delete only objects under the bucket's `sealed/` prefix. Keep the bucket, associated
object keys and document key consistent with the database backups. S3 is the production
document store. Keep the production configuration and bucket out of local development.

Run from the repository root on the VM:

```sh
docker compose --env-file deploy/.env -f deploy/compose.yml build
docker compose --env-file deploy/.env -f deploy/compose.yml up -d --wait db
docker compose --env-file deploy/.env -f deploy/compose.yml run --rm api alembic upgrade head
docker compose --env-file deploy/.env -f deploy/compose.yml up -d
docker compose --env-file deploy/.env -f deploy/compose.yml run --rm api python -m legal_api.corpus.statutes
```

The first corpus run downloads the embedding model. Later runs use its separate cache volume.
Load the optional local decision archive using the ingestion commands in
[Architecture](ARCHITECTURE.md#running-locally). With the current OpenRouter connection,
inference can send request and document excerpts to the model provider. See
[Client data protection](PRIVACY.md) to configure a protected deployment.

## Route and verify

Install `deploy/cloudflared.yml` at `/etc/cloudflared/legal-folonto.yml`, the existing tunnel's
credentials at `/etc/cloudflared/legal-folonto.json` (root-only mode 600), and
`deploy/legal-folonto-tunnel.service` under `/etc/systemd/system`. Set the config's tunnel field
to the tunnel UUID if the connector only has its JSON credentials. Enable the service and link
the proxied Cloudflare DNS record for `legal.folonto.com` to the tunnel UUID.

```sh
curl -fsS -H 'Host: legal.folonto.com' http://127.0.0.1:3100/api/health
curl -fsS https://legal.folonto.com/api/health
curl -fsS https://legal.folonto.com/api/ready
```

Verify an authenticated upload, byte-for-byte download, and deletion with a synthetic file.
Check the browser uses `/api` for same-origin requests. Confirm readiness after indexing.
