#!/bin/bash

cd /Users/vrishinarepalli/Desktop/Projects/Pokemon_showdown/PS

echo "Pulling latest changes..."
git pull

echo "Running 1 battle..."
python -m bot.agents.smoke_test_m4 --n-battles 1
