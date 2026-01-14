# SLAP Web API Reference

SLAP provides a REST API and WebSocket interface for controlling the scoreboard.

## Base URL

```
http://localhost:9876/api
```

## REST Endpoints

### Get State

Get the current system state including game data and connection status.

```
GET /api/state
```

**Response:**
```json
{
  "game": {
    "home": 3,
    "away": 2,
    "period": "2",
    "clock": "15:30",
    "home_penalties": [120],
    "away_penalties": [],
    "last_goal": "HOME",
    "last_update": "2024-01-15T19:30:45.123456"
  },
  "bug_visible": true,
  "replay_active": false,
  "serial_connected": true,
  "caspar_connected": true,
  "simulator_running": false
}
```

---

### Update State

Manually update the game state.

```
POST /api/state
Content-Type: application/json
```

**Request Body:**
```json
{
  "home": 4,
  "away": 2,
  "period": "3",
  "clock": "10:00",
  "home_penalties": [],
  "away_penalties": [120]
}
```

All fields are optional. Only provided fields will be updated.

**Response:**
```json
{
  "status": "ok",
  "state": { ... }
}
```

---

### Trigger Goal

Trigger a goal event with animation.

```
POST /api/goal
Content-Type: application/json
```

**Request Body:**
```json
{
  "side": "HOME"
}
```

| Field | Type | Values | Description |
|-------|------|--------|-------------|
| `side` | string | `"HOME"`, `"AWAY"` | Which team scored |

**Response:**
```json
{
  "status": "ok",
  "side": "HOME"
}
```

---

### Add Penalty

Add a penalty to a team.

```
POST /api/penalty
Content-Type: application/json
```

**Request Body:**
```json
{
  "side": "HOME",
  "duration": 120
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `side` | string | `"HOME"` | Team receiving penalty |
| `duration` | integer | `120` | Penalty duration in seconds |

Common durations:
- `120` = 2 minutes (minor)
- `300` = 5 minutes (major)

**Response:**
```json
{
  "status": "ok"
}
```

---

### Simulator Controls

#### Start Simulator
```
POST /api/simulator/start
```

#### Stop Simulator
```
POST /api/simulator/stop
```

#### Reset Simulator
```
POST /api/simulator/reset
```

**Response (all):**
```json
{
  "status": "ok"
}
```

---

### Scorebug Visibility

#### Show Scorebug
```
POST /api/bug/show
```

#### Hide Scorebug
```
POST /api/bug/hide
```

**Response (all):**
```json
{
  "status": "ok"
}
```

---

### Get Configuration

```
GET /api/config
```

**Response:**
```json
{
  "serial": {
    "port": "/dev/ttyUSB0",
    "baudrate": 9600
  },
  "caspar": {
    "host": "127.0.0.1",
    "port": 5250,
    "enabled": true
  },
  "web": {
    "port": 9876
  },
  "simulator": {
    "enabled": false
  },
  "home_team": {
    "name": "HOME",
    "color": "#0055AA"
  },
  "away_team": {
    "name": "AWAY",
    "color": "#AA0000"
  }
}
```

---

## WebSocket Interface

SLAP uses Socket.IO for real-time updates.

### Connection

```javascript
const socket = io('http://localhost:9876');

socket.on('connect', () => {
  console.log('Connected to SLAP');
});
```

### Events

#### `state_update`

Emitted whenever the game state changes.

```javascript
socket.on('state_update', (state) => {
  console.log('New state:', state);
  // state has same structure as GET /api/state response
});
```

#### `request_state`

Request current state from server.

```javascript
socket.emit('request_state');
// Server will respond with state_update event
```

#### `update_score`

Update scores via WebSocket.

```javascript
socket.emit('update_score', {
  home: 5,
  away: 3
});
```

#### `update_clock`

Update game clock.

```javascript
socket.emit('update_clock', {
  clock: "12:30"
});
```

#### `update_period`

Update period.

```javascript
socket.emit('update_period', {
  period: "3"
});
```

---

## Error Responses

All endpoints return errors in this format:

```json
{
  "error": "Error message description"
}
```

| Status Code | Description |
|-------------|-------------|
| 400 | Bad request (invalid parameters) |
| 503 | Service unavailable (e.g., simulator not enabled) |

---

## Example Usage

### cURL Examples

```bash
# Get current state
curl http://localhost:9876/api/state

# Trigger home goal
curl -X POST http://localhost:9876/api/goal \
  -H "Content-Type: application/json" \
  -d '{"side": "HOME"}'

# Set score manually
curl -X POST http://localhost:9876/api/state \
  -H "Content-Type: application/json" \
  -d '{"home": 3, "away": 1}'

# Start simulator
curl -X POST http://localhost:9876/api/simulator/start

# Add 2-minute penalty to away team
curl -X POST http://localhost:9876/api/penalty \
  -H "Content-Type: application/json" \
  -d '{"side": "AWAY", "duration": 120}'
```

### Python Example

```python
import requests

BASE_URL = "http://localhost:9876/api"

# Get state
state = requests.get(f"{BASE_URL}/state").json()
print(f"Score: {state['game']['home']} - {state['game']['away']}")

# Trigger goal
requests.post(f"{BASE_URL}/goal", json={"side": "HOME"})

# Update score
requests.post(f"{BASE_URL}/state", json={"home": 5, "away": 2})
```

### JavaScript Example

```javascript
// Using fetch API
async function triggerGoal(side) {
  const response = await fetch('/api/goal', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ side })
  });
  return response.json();
}

// Using Socket.IO for real-time updates
const socket = io();

socket.on('state_update', (state) => {
  document.getElementById('homeScore').textContent = state.game.home;
  document.getElementById('awayScore').textContent = state.game.away;
});
```

---

## Stream Deck Integration

SLAP's API is designed to work with Stream Deck and similar control surfaces.

### Recommended Button Actions

| Button | HTTP Request |
|--------|--------------|
| Home Goal | `POST /api/goal` with `{"side":"HOME"}` |
| Away Goal | `POST /api/goal` with `{"side":"AWAY"}` |
| Show Bug | `POST /api/bug/show` |
| Hide Bug | `POST /api/bug/hide` |
| Home +1 | `POST /api/state` with incremented home score |
| Away +1 | `POST /api/state` with incremented away score |

Use Stream Deck's "Website" action with HTTP requests, or use a plugin that supports REST APIs.
