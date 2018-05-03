
USER="dmack"
JOB_NAME="genetic_curriculum_$(date +%Y%m%d_%H%M%S)"
BUCKET_NAME="octavian-training"
REGION="us-central1"
GCS_PATH="${BUCKET_NAME}/${JOB_NAME}"
PROJECT_ID=$(gcloud config list project --format "value(core.project)")
 
gcloud ml-engine jobs submit training "$JOB_NAME" \
    --stream-logs \
    --module-name src.train \
    --package-path src \
    --staging-bucket "gs://${BUCKET_NAME}" \
    --region "$REGION" \
    --runtime-version=1.6 \
    --python-version=3.5 \
    --config "./gcloud-config.json" \
    -- \
    --output-dir "./output" \
    --gcs-dir "$JOB_NAME" \
    --bucket "$BUCKET_NAME" \
    --model-dir "gs://${BUCKET_NAME}/${JOB_NAME}/checkpoint"