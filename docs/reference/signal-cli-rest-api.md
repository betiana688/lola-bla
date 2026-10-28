# signal-cli-rest-api — Command Reference

Reference for the `bbernhard/signal-cli-rest-api` container used in this project (running via Docker, linked as a secondary device to Betiana's Signal account). All examples assume the container is reachable at `http://localhost:8080` from the Pi itself.

Full interactive docs (Swagger UI) are maintained by the project at:
https://bbernhard.github.io/signal-cli-rest-api/

> Replace `+491234567` below with the actual linked account number.

## Account & linking

| Purpose | Method & endpoint |
|---|---|
| List registered/linked accounts | `GET /v1/accounts` |
| Get a QR code to link as a secondary device | `GET /v1/qrcodelink?device_name=<name>` |
| Register a new number (primary device) | `POST /v1/register/{number}` |
| Verify a registered number (SMS code) | `POST /v1/register/{number}/verify/{code}` |
| Unregister a number | `POST /v1/unregister/{number}` |

## Receiving messages

| Purpose | Method & endpoint |
|---|---|
| Fetch new messages (poll/sync) | `GET /v1/receive/{number}` |

Note: in `native`/`normal` mode, this must be called regularly (polling) to stay in sync — `signal-cli` doesn't push new messages on its own unless running in `json-rpc` mode.

## Groups

| Purpose | Method & endpoint |
|---|---|
| List all groups | `GET /v1/groups/{number}` |
| Get details of one group | `GET /v1/groups/{number}/{groupId}` |
| Create a group | `POST /v1/groups/{number}` |
| Update a group (name, members, etc.) | `PUT /v1/groups/{number}/{groupId}` |
| Delete/leave a group | `DELETE /v1/groups/{number}/{groupId}` |
| Block a group | `POST /v1/groups/{number}/{groupId}/block` |

## Sending messages

| Purpose | Method & endpoint |
|---|---|
| Send a message (text and/or attachment) to recipients or a group | `POST /v2/send` |
| Send a reaction (emoji) to a message | `POST /v1/reactions/{number}` |
| Send a typing indicator | `PUT /v1/typing-indicator/{number}` |

`POST /v2/send` body example (text + attachment, to a group):
```json
{
  "message": "Hola!",
  "number": "+491234567",
  "recipients": ["group.XXXXXXXXXXXXXXXXXXXXXXXX="],
  "base64_attachments": ["<base64-encoded audio file>"]
}
```

## Attachments

| Purpose | Method & endpoint |
|---|---|
| List stored attachments | `GET /v1/attachments` |
| Download an attachment | `GET /v1/attachments/{attachmentId}` |
| Delete an attachment | `DELETE /v1/attachments/{attachmentId}` |

Incoming voice messages arrive as attachments referenced in the payload from `/v1/receive/{number}` — this project downloads them and stores the local file path in the `messages` table (`audio_path`).

## Contacts & profile

| Purpose | Method & endpoint |
|---|---|
| List contacts | `GET /v1/contacts/{number}` |
| Update a contact | `PUT /v1/contacts/{number}` |
| Update own profile (name/avatar) | `PUT /v1/profiles/{number}` |
| Search if a number is registered on Signal | `GET /v1/search?numbers={number}` |

## Execution modes (set via `MODE` env var on the container)

| Mode | Notes |
|---|---|
| `normal` | Default; JVM per request, slower |
| `native` | Uses the native binary; faster than `normal`, still per-request |
| `json-rpc` | Persistent daemon connection; pushes new messages, no manual polling needed |
| `json-rpc-native` | Combines native binary + persistent daemon; fastest option |

This project currently runs in `native` mode (set at container startup) and polls via `/v1/receive/{number}`. Switching to a `json-rpc` mode later would remove the need for manual polling — worth revisiting once the background sync (Step 5) is built.

---
*Curated for the Lola Reachy Signal app project — not exhaustive. See the official Swagger docs linked above for the complete, authoritative endpoint list.*
