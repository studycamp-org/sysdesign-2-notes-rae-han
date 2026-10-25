#!/usr/bin/env bash
# 템플릿 저장소의 최신 내용(새 챕터 등)을 내 저장소로 가져옵니다.
set -euo pipefail

TEMPLATE_URL="https://github.com/studycamp-org/sysdesign-2-template.git"

if ! git remote get-url template >/dev/null 2>&1; then
  echo "템플릿 원격 저장소를 등록합니다..."
  git remote add template "$TEMPLATE_URL"
fi

echo "템플릿 최신 내용을 가져옵니다..."
git fetch template

git merge template/main --no-edit --allow-unrelated-histories

echo "완료! 새로 추가된 내용을 확인하세요: git log --oneline -5"
