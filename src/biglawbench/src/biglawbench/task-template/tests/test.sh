#!/bin/bash
mkdir -p /logs/verifier
python3 /tests/judge.py --rubric /tests/rubric.md --answer /app/answer.md --out /logs/verifier/reward.txt
status=$?
if [ ! -f /logs/verifier/reward.txt ]; then
  echo 0 > /logs/verifier/reward.txt
fi
exit $status
