import ai_engine
import os

test_image = "uploads/1769527229.271653_meal_764119001.jpg"

try:
    print(f"Testing AI with image: {test_image}")
    food, cals = ai_engine.estimate_calories(test_image)
    print(f"Result - Food: {food}, Calories: {cals}")
except Exception as e:
    print(f"Error during AI test: {e}")
