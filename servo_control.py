import RPi.GPIO as GPIO
import time

# Pin setup
SERVO_PIN = 15  # GPIO pin where servo signal wire is connected

# GPIO setup
GPIO.setmode(GPIO.BOARD)  # Using physical pin numbering
GPIO.setup(SERVO_PIN, GPIO.OUT)

# Set PWM frequency (typical servo uses 50Hz)
pwm = GPIO.PWM(SERVO_PIN, 50)
pwm.start(0)

def set_angle(angle):
    """Move servo to a specific angle (0-180)."""
    duty = 2 + (angle / 18)  # Map angle to duty cycle
    GPIO.output(SERVO_PIN, True)
    pwm.ChangeDutyCycle(duty)
    time.sleep(0.5)  # Let servo move
    GPIO.output(SERVO_PIN, False)
    pwm.ChangeDutyCycle(0)

try:
    print("Moving servo to block LEFT path...")
    set_angle(45)   # Move a little to the right (blocks left path)

    time.sleep(2)

    print("Moving servo further to block LEFT + MIDDLE paths...")
    set_angle(90)   # Move further to the middle

    time.sleep(2)

    print("Returning servo to neutral position...")
    set_angle(0)    # Back to neutral (optional)

finally:
    pwm.stop()
    GPIO.cleanup()
