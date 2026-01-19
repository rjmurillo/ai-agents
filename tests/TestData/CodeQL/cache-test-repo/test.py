import os
import subprocess

def run_command(user_input):
    # Intentional vulnerability for testing
    subprocess.call(user_input, shell=True)
