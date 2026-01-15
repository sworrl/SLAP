/**
 * SLAP Hockey Scorebug - CasparCG Template Script
 *
 * Handles data updates from CasparCG AMCP protocol and WebSocket.
 * Compatible with both CasparCG server and SLAP web preview.
 */

// Global state
var dataCaspar = {};
var currentState = {
    home: 0,
    away: 0,
    period: "1",
    clock: "20:00",
    home_penalties: [],
    away_penalties: []
};

/**
 * Escape HTML special characters to prevent XSS
 */
function escapeHtml(unsafe) {
    if (typeof unsafe !== 'string') return unsafe;
    return unsafe
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

/**
 * Parse CasparCG XML templateData string
 */
function parseCaspar(str) {
    try {
        var parser = new DOMParser();
        var xmlDoc = parser.parseFromString(str, "text/xml");
        dataCaspar = XML2JSON(xmlDoc.documentElement.childNodes);
    } catch (e) {
        console.error("Failed to parse CasparCG data:", e);
    }
}

/**
 * Convert XML nodes to JSON object
 */
function XML2JSON(nodes) {
    var data = {};
    for (var i = 0; i < nodes.length; i++) {
        var node = nodes[i];
        if (node.nodeType !== 1) continue; // Skip non-element nodes

        var id = node.getAttribute("id");
        var valueNode = node.querySelector("data[value]") || node.childNodes[0];
        var value = valueNode ? valueNode.getAttribute("value") : null;

        if (id && value !== null) {
            data[id] = value;
        }
    }
    return data;
}

/**
 * Insert data into DOM elements by ID
 */
function dataInsert(data) {
    for (var id in data) {
        var element = document.getElementById(id);
        if (element) {
            element.innerHTML = escapeHtml(data[id]);
        }
    }
}

/**
 * Format period for display
 */
function formatPeriod(period) {
    var p = String(period).toUpperCase();
    if (p === "1") return "1ST";
    if (p === "2") return "2ND";
    if (p === "3") return "3RD";
    if (p === "OT" || p === "4") return "OT";
    if (p === "SO") return "SO";
    return p;
}

/**
 * Format seconds to MM:SS
 */
function formatTime(seconds) {
    var m = Math.floor(seconds / 60);
    var s = seconds % 60;
    return m + ":" + (s < 10 ? "0" : "") + s;
}

/**
 * Update display from JSON game state
 */
function updateFromJSON(data) {
    // Store current state
    var prevHome = currentState.home;
    var prevAway = currentState.away;

    currentState = Object.assign(currentState, data);

    // Update scores
    var homeScore = document.getElementById("t1Score");
    var awayScore = document.getElementById("t2Score");

    if (homeScore) homeScore.textContent = currentState.home;
    if (awayScore) awayScore.textContent = currentState.away;

    // Goal flash animation
    if (currentState.home > prevHome && homeScore) {
        homeScore.parentElement.classList.add("goal");
        setTimeout(function() {
            homeScore.parentElement.classList.remove("goal");
        }, 1500);
    }
    if (currentState.away > prevAway && awayScore) {
        awayScore.parentElement.classList.add("goal");
        setTimeout(function() {
            awayScore.parentElement.classList.remove("goal");
        }, 1500);
    }

    // Update period
    var period = document.getElementById("period");
    if (period) period.textContent = formatPeriod(currentState.period);

    // Update clock
    var clock = document.getElementById("gameClock");
    if (clock) clock.textContent = currentState.clock;

    // Update power play indicators
    updatePowerPlay();
}

/**
 * Update power play dropdown visibility
 */
function updatePowerPlay() {
    var homePens = currentState.home_penalties || [];
    var awayPens = currentState.away_penalties || [];

    var team1PP = document.getElementById("team1-pp");
    var team2PP = document.getElementById("team2-pp");
    var t1Logo = document.getElementById("t1Logo");
    var t1Name = document.getElementById("t1Name");

    // Home has power play when away has more penalties
    if (awayPens.length > homePens.length && awayPens.length > 0) {
        if (team1PP) team1PP.classList.add("open");
        if (t1Logo) t1Logo.classList.add("pp");
        if (t1Name) t1Name.classList.add("pp");

        var t1PPTime = document.getElementById("t1PP");
        if (t1PPTime && awayPens[0]) {
            t1PPTime.textContent = formatTime(awayPens[0]);
        }
    } else {
        if (team1PP) team1PP.classList.remove("open");
        if (t1Logo) t1Logo.classList.remove("pp");
        if (t1Name) t1Name.classList.remove("pp");
    }

    // Away has power play when home has more penalties
    if (homePens.length > awayPens.length && homePens.length > 0) {
        if (team2PP) team2PP.classList.add("open");

        var t2PPTime = document.getElementById("t2PP");
        if (t2PPTime && homePens[0]) {
            t2PPTime.textContent = formatTime(homePens[0]);
        }
    } else {
        if (team2PP) team2PP.classList.remove("open");
    }
}

// ============ CasparCG AMCP Interface ============

/**
 * Called by CasparCG to update template data (no animation)
 */
function update(str) {
    // Check if JSON or XML
    if (str.trim().startsWith("{")) {
        try {
            var data = JSON.parse(str);
            updateFromJSON(data);
        } catch (e) {
            console.error("Failed to parse JSON:", e);
        }
    } else {
        parseCaspar(str);
        dataInsert(dataCaspar);
    }
}

/**
 * Called by CasparCG to play template (with intro animation)
 */
function play(str) {
    var scorebug = document.getElementById("scorebug");
    if (scorebug) {
        scorebug.classList.remove("hidden", "outro");
        scorebug.classList.add("intro");
    }

    if (str) {
        update(str);
    }
}

/**
 * Called by CasparCG to stop template (with outro animation)
 */
function stop() {
    var scorebug = document.getElementById("scorebug");
    if (scorebug) {
        scorebug.classList.remove("intro");
        scorebug.classList.add("outro");
    }
}

/**
 * Called by CasparCG INVOKE for custom actions
 */
function invoke(action) {
    var parts = action.split(":");
    var cmd = parts[0];
    var arg = parts[1];

    switch (cmd) {
        case "goal":
            triggerGoal(arg);
            break;
        case "show":
            play();
            break;
        case "hide":
            stop();
            break;
        case "powerplay":
            // Toggle power play manually if needed
            break;
    }
}

/**
 * Trigger goal animation
 */
function triggerGoal(side) {
    var scoreEl = side === "HOME"
        ? document.getElementById("t1Score")
        : document.getElementById("t2Score");

    if (scoreEl) {
        var parent = scoreEl.parentElement;
        parent.classList.add("goal");
        setTimeout(function() {
            parent.classList.remove("goal");
        }, 1500);
    }
}

// ============ Web Preview Interface ============

/**
 * Called from parent window (SLAP dashboard)
 */
function updateFromParent(data) {
    updateFromJSON(data);
}

/**
 * Apply team configuration (colors, names, logos)
 */
function applyTeamConfig(config) {
    var root = document.documentElement;

    if (config.home) {
        // Update home team colors
        if (config.home.primary_color) {
            root.style.setProperty('--home-primary', config.home.primary_color);
        }
        if (config.home.secondary_color) {
            root.style.setProperty('--home-secondary', config.home.secondary_color);
        }
        // Update home team name
        if (config.home.name) {
            var t1Name = document.getElementById('t1Name');
            if (t1Name) t1Name.textContent = config.home.name;
        }
        // Update home team logo
        if (config.home.logo) {
            var t1Logo = document.querySelector('#t1Logo img');
            if (t1Logo) t1Logo.src = 'Logos/' + config.home.logo;
        }
    }

    if (config.away) {
        // Update away team colors
        if (config.away.primary_color) {
            root.style.setProperty('--away-primary', config.away.primary_color);
        }
        if (config.away.secondary_color) {
            root.style.setProperty('--away-secondary', config.away.secondary_color);
        }
        // Update away team name
        if (config.away.name) {
            var t2Name = document.getElementById('t2Name');
            if (t2Name) t2Name.textContent = config.away.name;
        }
        // Update away team logo
        if (config.away.logo) {
            var t2Logo = document.querySelector('#t2Logo img');
            if (t2Logo) t2Logo.src = 'Logos/' + config.away.logo;
        }
    }
}

// Listen for messages from parent window
window.addEventListener('message', function(event) {
    if (event.data && event.data.type === 'team_config') {
        applyTeamConfig(event.data.data);
    }
});

// ============ WebSocket Connection (Standalone) ============

if (typeof io !== 'undefined') {
    var socket = io();

    socket.on('connect', function() {
        console.log('Connected to SLAP server');
    });

    socket.on('state_update', function(state) {
        if (state && state.game) {
            updateFromJSON(state.game);
        }
    });
}

// Initialize with default state
document.addEventListener('DOMContentLoaded', function() {
    updateFromJSON(currentState);
});
