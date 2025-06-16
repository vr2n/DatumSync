#!/bin/bash

# CONFIGURATION
PROJECT_ID="vr2n-462810"
BUCKET_NAME="datumsync"
TOPIC_NAME="gcs-upload-topic"
SUBSCRIPTION_NAME="gcs-upload-sub"
SERVICE_NAME="datum-normalizer"
REGION="asia-south1"

echo "⏳ Enabling required services..."
gcloud services enable \
  storage.googleapis.com \
  pubsub.googleapis.com \
  run.googleapis.com \
  eventarc.googleapis.com \
  --project=$PROJECT_ID

echo "✅ Creating Pub/Sub topic: $TOPIC_NAME"
gcloud pubsub topics create $TOPIC_NAME --project=$PROJECT_ID

echo "✅ Configuring GCS bucket to publish to topic on file finalize..."
gsutil notification create -t $TOPIC_NAME -f json -e OBJECT_FINALIZE gs://$BUCKET_NAME

echo "✅ Creating subscription: $SUBSCRIPTION_NAME"
gcloud pubsub subscriptions create $SUBSCRIPTION_NAME \
  --topic=$TOPIC_NAME \
  --ack-deadline=60 \
  --project=$PROJECT_ID

echo "🔐 Granting Pub/Sub permission to invoke Cloud Run"
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format="value(projectNumber)")
gcloud run services add-iam-policy-binding $SERVICE_NAME \
  --region=$REGION \
  --member="serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-pubsub.iam.gserviceaccount.com" \
  --role="roles/run.invoker" \
  --project=$PROJECT_ID

echo "🚀 Creating Pub/Sub trigger to call Cloud Run service..."
gcloud eventarc triggers create gcs-upload-pubsub-trigger \
  --location=$REGION \
  --destination-run-service=$SERVICE_NAME \
  --destination-run-region=$REGION \
  --transport-topic=projects/$PROJECT_ID/topics/$TOPIC_NAME \
  --project=$PROJECT_ID \
  --service-account="service-${PROJECT_NUMBER}@gcp-sa-eventarc.iam.gserviceaccount.com"

echo "🎉 Setup complete. Upload a file to gs://$BUCKET_NAME to test."
