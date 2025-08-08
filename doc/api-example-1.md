## Example of API usage

This example shows how to:

- create users, Alice and Bob
- create tasks, 001 and 002
- assign task to users, 001 to Alice and 002 to Bob

Data files are in [doc](.) directory.

```bash
HDR="Content-Type: application/json"
URL="http://localhost:8080"

curl -X POST -H "$HDR" "$URL/types" -d @type-user.json
curl -X POST -H "$HDR" "$URL/objects/user_type" -d @obj-user-alice.json
curl -X POST -H "$HDR" "$URL/objects/user_type" -d @obj-user-bob.json

curl -X POST -H "$HDR" "$URL/types" -d @type-task.json
curl -X POST -H "$HDR" "$URL/objects/task_type" -d @obj-task-001.json
curl -X POST -H "$HDR" "$URL/objects/task_type" -d @obj-task-002.json
```
