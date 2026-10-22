# Generated movement reference match

Schema 1.8, seed 0, normal 45-minute halves plus event-derived added time. This is the current full-match demonstration of support movement, carrying, lead passes, player runs during flight and recorded restart/recovery paths. Priorities 1-3 remain active. Existing legacy/P1/P2/P3 fixtures are preserved separately.

```powershell
py -3.13 -m simulator.ui_server --input data/examples/movement-match --port 8080
```

Open http://127.0.0.1:8080/ and keep Smooth enabled to interpolate between generated samples. Use [the complete UI handoff](../../../docs/UI-INTEGRATION.md) and [movement model/evaluation](../../../docs/REALISM-AND-MOVEMENT.md). The local bridge also provides current player ratings at /api/state?time_ms=... .

Inspect player_motion for generated active-player samples during control and flight. Movement and reposition records do not create pass/shot/rating action credit. Always draw the ball from ball_trajectory, preserve legal receipt timing, and evaluate offside from original teammate-contact positions rather than lead targets.

summary.json contains final values for recap/comparison only. evaluation-only.json is generator debugging and must not become detected intelligence. This is an uncalibrated original synthetic model, not real player tracking. The large JSONL fixture is intentional: it includes generated movement throughout the match.
