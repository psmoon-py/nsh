"""
Physical constants and configuration for the ACM.
All values from the problem statement.
"""

# Earth parameters
MU = 398600.4418          # km³/s² — Earth's gravitational parameter
RE = 6378.137             # km — Earth's equatorial radius
J2 = 1.08263e-3           # J2 perturbation coefficient
EARTH_ROTATION_RATE = 7.2921159e-5  # rad/s — Earth's angular velocity

# Spacecraft parameters
DRY_MASS = 500.0          # kg
INITIAL_FUEL = 50.0       # kg
INITIAL_WET_MASS = 550.0  # kg (dry + fuel)
ISP = 300.0               # seconds — specific impulse
G0 = 9.80665              # m/s² — standard gravity
MAX_DELTA_V = 0.015       # km/s (= 15 m/s per burn)
COOLDOWN_SECONDS = 600    # seconds between burns on same satellite
SIGNAL_DELAY = 10         # seconds — command transmission latency

# Conjunction thresholds
COLLISION_THRESHOLD = 0.100   # km (= 100 meters)
WARNING_THRESHOLD_RED = 1.0   # km (< 1 km = RED)
WARNING_THRESHOLD_YELLOW = 5.0  # km (< 5 km = YELLOW)
SCREENING_RADIUS = 500.0     # km — kept for legacy compatibility

# Linearized gate parameters (forecast-based screening)
LINEAR_GATE_MAX_MISS_KM = 20.0         # primary gate: keep if linear TCA miss < 20 km
LINEAR_GATE_RELAXED_MISS_KM = 50.0     # relaxed gate for soon encounters
MAX_SCREEN_CANDIDATES_PER_SAT = 64     # max debris per satellite after linearised gate
WATCHLIST_MISS_KM = 10.0               # keep on watchlist if miss < 10 km
WATCHLIST_TCA_SECONDS = 3600.0         # keep on watchlist if TCA < 1 hour

# Station-keeping
SLOT_TOLERANCE = 10.0     # km — max drift from nominal slot
EOL_FUEL_THRESHOLD = 0.05 # 5% of initial fuel

# Uptime scoring
UPTIME_DECAY_TAU_SECONDS = 3600.0  # exponential decay time constant

# Prediction horizon
PREDICTION_HORIZON = 86400  # seconds (24 hours)
FULL_CA_REFRESH_SECONDS = 300.0  # only re-run full conjunction assessment every 5 min

# Propagation
RK4_TIMESTEP = 10.0       # seconds — default integration step

# History for frontend
TRACK_HISTORY_MINUTES = 90
TRACK_PREDICTION_MINUTES = 90
TRACK_SAMPLE_SECONDS = 60.0
METRICS_SAMPLE_SECONDS = 60.0

# Snapshot / frontend
SNAPSHOT_DEFAULT_DEBRIS_LIMIT = 10000
SNAPSHOT_MAX_CDM = 100
SNAPSHOT_MAX_QUEUE = 200

# Collision refinement within sim step
INTERVAL_COLLISION_NEARBY_KM = 5.0
