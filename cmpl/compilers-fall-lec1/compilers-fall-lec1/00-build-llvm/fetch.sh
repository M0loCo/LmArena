#!/bin/sh
set -e
LLVM_TAG="${LLVM_TAG:-llvmorg-17.0.6}"

if [ -d llvm-project ]; then
    echo "llvm-project уже существует - пропускаю"
    exit 0
fi

git clone --depth 1 --branch "$LLVM_TAG" \
    https://github.com/llvm/llvm-project.git
