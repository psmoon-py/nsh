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
WARNING_THRESHOLD_RED = 1.0   # km (< 1 km = CRITICAL)
WARNING_THRESHOLD_YELLOW = 5.0  # km (< 5 km = WARNING)
SCREENING_RADIUS = 500.0     # km — KD-tree coarse screening radius

# Station-keeping
SLOT_TOLERANCE = 10.0     # km — max drift from nominal slot
EOL_FUEL_THRESHOLD = 0.05 # 5% of initial fuel

# Prediction horizon
PREDICTION_HORIZON = 86400  # seconds (24 hours)

# Propagation
RK4_TIMESTEP = 10.0       # seconds — default integration step
