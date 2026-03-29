#!/bin/bash

# Publish Script for Liberty Classifier

echo "----------------------------------------------------"
echo "  Liberty Classifier - Docker Publisher"
echo "----------------------------------------------------"
echo ""
echo "This script will help you share this application with others."
echo "Prerequisite: You must have a Docker Hub account (https://hub.docker.com/)."
echo ""

# 1. Get Username
read -p "Enter your Docker Hub Username: " DOCKER_USER
if [ -z "$DOCKER_USER" ]; then
    echo "Error: Username cannot be empty."
    exit 1
fi

IMAGE_NAME="liberty-classifier"
FULL_IMAGE="$DOCKER_USER/$IMAGE_NAME:latest"

echo ""
echo "Step 1: Logging in to Docker Hub..."
docker login

if [ $? -ne 0 ]; then
    echo "Login failed. Please try again."
    exit 1
fi

echo ""
echo "Step 2: Building the Image..."
# Build for multiple platforms (optional, but good for Mac/Windows compatibility if using buildx, 
# strictly simple build for now to avoid complexity)
docker build -t $IMAGE_NAME .
docker tag $IMAGE_NAME $FULL_IMAGE

echo ""
echo "Step 3: Pushing to Docker Hub ($FULL_IMAGE)..."
docker push $FULL_IMAGE

if [ $? -eq 0 ]; then
    echo ""
    echo "----------------------------------------------------"
    echo "  SUCCESS! Your app is published."
    echo "----------------------------------------------------"
    echo "Others can run it simply by typing:"
    echo ""
    echo "  docker run -p 5000:5000 $FULL_IMAGE"
    echo ""
else
    echo "Error: Failed to push image."
fi
