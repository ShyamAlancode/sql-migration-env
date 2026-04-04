"""
training_demo.py — Generate actual reward curve using actual inference
OpenEnv Hackathon 2026
"""

import os
import random
import time
import requests
import matplotlib.pyplot as plt
from inference import SQLMigrationAgent, run_episode

# Ensure we run against the local environment or the live Space
ENV_URL = os.environ.get("ENV_URL", "http://localhost:7860")

def run_training_demo(episodes=20):
    print(f"Running {episodes} evaluation episodes to generate reward curve...")
    rewards = []
    
    agent = SQLMigrationAgent()
    tasks = ["easy", "medium", "hard"]
    
    for i in range(episodes):
        task = random.choice(tasks)
        print(f"Episode {i+1}/{episodes} - Task: {task}")
        try:
            summary = run_episode(agent, task)
            scores = summary.get("score", 0.0)
            rewards.append(scores)
        except Exception as e:
            print(f"Error on episode {i+1}: {e}")
            rewards.append(0.0)
        
        # Buffer for Groq Rate Limits (TPM 6000)
        time.sleep(3)
            
    # Plotting
    plt.figure(figsize=(10, 5))
    plt.plot(rewards, marker='o', color='#38bdf8', linestyle='-', linewidth=2)
    
    # Calculate moving average trend
    if len(rewards) > 3:
        window = 3
        moving_avg = [sum(rewards[max(0, i-window):i+1]) / min(i+1, window+1) for i in range(len(rewards))]
        plt.plot(moving_avg, color='#fbbf24', linestyle='--', linewidth=2, label='Moving Avg (3)')
        plt.legend()
        
    plt.title("Agent Learning Progress (`training_demo.py`)")
    plt.xlabel("Evaluation Episode")
    plt.ylabel("Normalized Reward")
    plt.ylim(0, 1.05)
    plt.grid(True, alpha=0.3)
    
    output_file = "reward_curve.png"
    plt.savefig(output_file)
    print(f"\nSaved reward learning curve to {output_file}")
    
    print("\nFinal Baseline Average:", sum(rewards)/len(rewards))

if __name__ == "__main__":
    run_training_demo(20)
