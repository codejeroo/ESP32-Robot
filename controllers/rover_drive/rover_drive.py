"""Drive the 4-wheel rover straight forward along +X, forever.

Wheel hinge axes are mirrored (left wheels along -Y, right wheels along +Y),
so a positive motor velocity spins the right wheels forward and the left
wheels backward. Forward motion therefore needs -v on the left motors and
+v on the right motors.
"""

from controller import Robot

MOTOR_NAMES = [
    "front_left_wheel",
    "back_left_wheel",
    "front_right_wheel",
    "back_right_wheel",
]

# Motor limit is 10 rad/s; wheel radius is 0.0335 m -> about 0.27 m/s.
MAX_VELOCITY = 8.0

robot = Robot()
timestep = int(robot.getBasicTimeStep())

for name in MOTOR_NAMES:
    motor = robot.getDevice(name)
    motor.setPosition(float("inf"))  # switch to velocity control mode
    sign = -1.0 if "left" in name else 1.0
    motor.setVelocity(sign * MAX_VELOCITY)

while robot.step(timestep) != -1:
    pass
