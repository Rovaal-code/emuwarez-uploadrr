#!/usr/bin/env python3
"""Fake Uploadrr script for Phase 9B controlled E2E testing.

Simulates the output of a successful Uploadrr execution.
Accepts any arguments without error. Makes no network requests.
Never touches real API keys, real uploads, or Uploadrr/.
"""
import sys

print("Upload completed")
print("Torrent URL: https://emuwarez.example/torrents/12345")
print("Torrent ID: 12345")
sys.exit(0)
