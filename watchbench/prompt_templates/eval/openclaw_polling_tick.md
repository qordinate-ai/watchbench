You are evaluating a timer-based inbox-monitoring agent.

The user has configured a set of watches. A watch is a precise condition for
when the user wants the agent to wake up and notify them about an email.

You are given only the emails that arrived since the previous timer tick. For
each email, decide whether it satisfies any watch. Return no wake for near
matches.

Stream user:
$stream_user_json

Registered watches:
$watches_json

New emails since previous timer tick:
$events_json

Return JSON only, exactly in this shape:
[
  {
    "watch_id": "watch_001",
    "event_id": "email_0001",
    "should_wake": true,
    "reason": "short reason"
  }
]

If no watch should wake, return [].
