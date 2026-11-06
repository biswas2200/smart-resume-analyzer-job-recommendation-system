# Settings shared by the laptop-side scripts in this folder (sourced, not run).
# vm.sh runs on the VM, where there is no git checkout, and keeps its own.

PROJECT=${PROJECT:-smart-resume-analyzer-a7x2}
REGION=${REGION:-asia-south1}
ZONE=${ZONE:-asia-south1-a}
BUCKET=${BUCKET:-gs://smart-resume-analyzer-a7x2-data}
VM=${VM:-data-prep-vm}
SA=data-prep@$PROJECT.iam.gserviceaccount.com
ROOT=$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)

# Fingerprint of the code the VM runs: every committed .py and .sh file under ml-service.
# push_code.sh writes it into the VM's VERSION file; preflight.sh compares the two.
code_fingerprint() {
  git -C "$ROOT" ls-tree -r HEAD -- ml-service | awk '$4 ~ /\.(py|sh)$/ {print $3, $4}' | sha256sum | cut -c1-16
}

uncommitted_code() { git -C "$ROOT" status --porcelain -- ml-service | grep -E '\.(py|sh)$'; }
