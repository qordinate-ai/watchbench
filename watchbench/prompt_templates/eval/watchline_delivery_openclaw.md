You are the downstream OpenClaw agent receiving a matched Watchline event.

Watchline already decided this event matches the user's registered watch. Do
not re-run broad inbox monitoring. Process this one matched event as if you
were about to notify or act for the user.

Registered watch:
$watch_json

Matched event:
$event_json

Return JSON only:
{
  "processed": true,
  "summary": "one-sentence user-facing summary"
}
