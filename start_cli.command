#!/bin/bash
# EQ Cosplay 终端版入口
cd "$(dirname "$0")"
exec bash "$(dirname "$0")/start.command" --cli
