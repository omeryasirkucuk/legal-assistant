# Deploying legal.folonto.com

The Oracle ARM VM also hosts the Defter stack. Legal Assistant uses its own Compose project,
Postgres volume, Cloudflare Tunnel and S3 bucket. The only Legal port mapped on the VM is
`127.0.0.1:3100`. Cloudflare forwards `legal.folonto.com` to that port over the tunnel.
The proxy redirects HTTP to HTTPS. Postgres and the API are reachable within the Compose network.

## Configure and release

Place the checkout at `/opt/legal-folonto` with Docker, Docker Compose and the Buildx plugin installed.
On the Ubuntu VM, install the plugin with `sudo apt-get install docker-buildx`. Copy
`deploy/.env.example` to `deploy/.env` with mode 600. Set a random hex Postgres password,
an independent random session secret, and an independent 32-byte URL-safe base64 document
encryption key. Save a recovery copy of the encryption key separately. For a fresh database,
use a strong private `INVITE_CODE` to register the first administrator, then remove the
bootstrap code from the environment. Create single-use, email-bound codes for additional
users in **Yönetim paneli → Yeni kullanıcı daveti**.

Enable S3 Block Public Access for the bucket. Give the API identity permission to get, put
and delete only objects under the bucket's `sealed/` prefix. Keep the bucket, associated
object keys and document key consistent with the database backups. S3 is the production
document store. Keep the production configuration and bucket out of local development.

Install the tunnel configuration below before the first release. Run the release script
from the repository root on the VM:

```sh
sudo bash deploy/release.sh
```

The script locks the release, saves the currently healthy API and web images,
builds the new images, migrates the database and starts the stack. It indexes
the core statutes if readiness requires it. After the local health and public health,
readiness and sign-in checks pass, it keeps the previous serving pair as `:rollback`,
removes unused older Folonto API and web images
and expires unused cache from the VM's default Docker builder, targeting 1 GB of total cache.
It protects images attached to containers, the new images and the previous serving pair.
The PostgreSQL and model volumes stay in place.

To run the same verified cleanup against an existing release on the Oracle VM:

```sh
sudo bash deploy/release.sh --cleanup-only
```

For a rollback where the database schema still supports the previous release, tag the
saved `legal-folonto-api:rollback` and `legal-folonto-web:rollback` images as `:latest`,
run Compose with `up -d --no-build api web` using the production env file and Compose file,
and verify the endpoints below. For a schema rollback, follow the matching database recovery plan.

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
