# Client data protection

Use development mode with synthetic material. Protected mode is intended for an operator who
controls the API, database, document volume and inference endpoint. The account owner keeps
the full answer, case material and exports in the authenticated workspace. Use the smallest
set of relevant files and excerpts for each request. Opening a public source is a deliberate
browser action. Client-derived search terms stay in the local indexes.

## Data and access

| Data | Where it goes |
| --- | --- |
| Original files and generated exports | The API encrypts payloads with AES-256-GCM, using the owning account and file UUID as associated data. The filesystem path or optional private S3 key uses identifiers in place of the filename. |
| Extracted text, filenames, case notes, chats, drafts and style samples | Postgres, scoped to the account. Use an encrypted Postgres volume and encrypted backups. The database can search these fields while mounted and must be accessible only to authorized services and operators. |
| The current request, relevant case excerpts and the conversation context | The protected model endpoint configured on the server. Configure its logging, retention, downstream services and access as part of the same boundary. |
| Public statutes and decisions | Local statute and decision indexes. Run corpus updates as separate jobs using public law numbers and public datasets. |
| Operational records | Model spending keeps account, purpose, amount and time. Keep application, proxy and inference logs free of request bodies, document names and answer text. |

Protected mode disables OpenRouter routing, the external decision model, case-derived live
source requests and UI changes to the inference endpoint. Quote matching and quantity checks
still run in the API. Case law coverage depends on the local decision corpus. Configure and
test the compatible endpoint with synthetic Turkish matters before use. The current compatible
provider path sends text. Keep scanned documents and images available to the user in the file
viewer and provide extracted text when their contents are needed for an answer.

## Enable protected mode

1. Configure encrypted storage for Postgres, its WAL and the API's temporary upload files.
   Use encrypted local disks or a private temporary filesystem for multipart spooling. Disable
   plaintext request spooling and body logging at the reverse proxy. Keep the API and database
   on a private network and use HTTPS on the browser-facing origin.
2. Generate a new 32-byte document key and store it as URL-safe base64 in the deployment's
   secret store. Use a separate random `SECRET_KEY` of at least 32 characters for sessions and
   saved credentials. Keep independent recovery copies of both secrets. Restrict access to the
   API identity and authorized operators. Never share the keys with the inference endpoint.
3. Set `PRIVATE_MODEL_BASE_URL` to the reviewed OpenAI-compatible service. Use loopback HTTP
   for a model on the same host or HTTPS for a service on another host. Set
   `PRIVATE_MODEL_API_KEY` if required. Set each `OPENAI_MODEL_*` variable to an available
   model. Review the selected endpoint's sub-processors and any upstream routing separately.
4. Set `COOKIE_SECURE=true`. Set `WEB_ORIGINS` to a JSON list of the web origins if the API is
   served from another origin on the same site. For a same-origin proxy, set `NEXT_PUBLIC_API_URL=/api` in
   `apps/web/.env.local` before building and strip the `/api` prefix at the proxy. Close public
   registration by clearing `INVITE_CODE` after enrollment.
5. Take a recoverable backup of the existing deployment in maintenance mode. Stop API writes,
   run `make migrate`, then run the seal operation with `DOCUMENT_ENCRYPTION_KEY` set.

   ```sh
   cd services/api
   uv run --locked python -m legal_api.files.encrypt
   ```

   The operation verifies each payload against its stored hash, commits its new path and then
   removes the old plaintext copy. Run the same command again after an interruption. Keep the
   API offline until the command finishes, including cleanup. Protected mode refuses to start
   while legacy unencrypted rows or payloads remain. Reconcile orphaned legacy payloads with the
   backup inventory and the deployment's retention decisions before starting.
6. Set `DATA_MODE=protected`, start the application with `make api-protected` and check `/ready`.
   Use a synthetic
   account to test upload, download, case chat and export. Verify cross-account isolation and
   demonstrate that the model handles a request without sending it to another provider. Require
   authorization at the network boundary for the API host's outbound traffic as well. Keep
   access logs disabled or remove query strings at every layer, since search terms can be private.

## Back up and restore

Take a consistent snapshot of Postgres and `STORAGE_DIR` with writes stopped, or use coordinated
storage snapshots with an equivalent consistency guarantee. With `S3_BUCKET` enabled,
include the corresponding encrypted S3 objects and retain their original keys in the backup. Set the Postgres client connection
with `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER` and a restricted `PGPASSFILE` or equivalent secret
mechanism. Use a backup public key whose private key stays in an independent recovery store.
In the examples, `BACKUP_DIR` is a fresh private directory and `BACKUP_RECIPIENT` is the verified
fingerprint of that key. Use a shell that supports `pipefail`.

```bash
set -euo pipefail
umask 077
mkdir "$BACKUP_DIR"
pg_dump --format=custom | gpg --batch --encrypt --recipient "$BACKUP_RECIPIENT" \
  --output "$BACKUP_DIR/postgres.gpg"
tar -C "$STORAGE_DIR" -czf - . | gpg --batch --encrypt --recipient "$BACKUP_RECIPIENT" \
  --output "$BACKUP_DIR/storage.tar.gpg"
```

Publish the snapshot after both commands succeed. Keep it in restricted, versioned backup
storage with an operator-defined expiration policy. Store the document and session keys as
separate encrypted secrets. Previously taken snapshots may hold plaintext payloads inside
their encrypted archive and follow the old snapshot's access and retention policy.

Test recovery into an isolated empty database and a fresh private storage directory. Use the
PG environment for the restore target and provide the GPG private key through the recovery
keyring. Verify both archives before restoring into staging.

```bash
set -euo pipefail
umask 077
gpg --decrypt "$BACKUP_DIR/postgres.gpg" >/dev/null
gpg --decrypt "$BACKUP_DIR/storage.tar.gpg" >/dev/null
mkdir "$RESTORE_STORAGE_DIR"
gpg --decrypt "$BACKUP_DIR/postgres.gpg" | pg_restore --exit-on-error --single-transaction \
  --no-owner --no-privileges --dbname "$PGDATABASE"
gpg --decrypt "$BACKUP_DIR/storage.tar.gpg" | tar -C "$RESTORE_STORAGE_DIR" -xzf -
```

Run migrations up to the restored app version, supply the restored document key and confirm that
a known synthetic file can be decrypted and downloaded. Check `/ready` and reconcile any live
deletion decisions before putting a restored system back into service. Record which backup was
tested, its restore time and the result. Do not replace a production database without verifying
the recovery first.

## Review the actual deployment

Before processing client data, the responsible operator should document the processing purposes,
roles, legal basis, sensitive-data handling, retention and deletion workflow, data subject contact
and incident response. Make the deployment's own privacy notice available to users. Record where
the model runs and the recipients of any onward transfer. For cross-border processing, review
the applicable transfer mechanism and any required filing under the current rules. A user sending
a message is a product action. The operator is responsible for determining the basis for handling
both the user's and third parties' information. Review professional secrecy obligations alongside
the data protection assessment.

- [KVKK application guide for lawyers](https://www.kvkk.gov.tr/SharedFolderServer/CMSFiles/MTZhYjI0ZTE1NWIwMWM.pdf)
- [KVKK guidance on transfers abroad](https://www.kvkk.gov.tr/Icerik/2053/Yurtdisina-Aktarim)
- [KVKK security obligations and technical guidance](https://www.kvkk.gov.tr/Icerik/2040/Veri-Guvenligine-Iliskin-Yukumlulukler)
