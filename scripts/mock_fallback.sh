#!/usr/bin/env bash
# Simulates a provider fallback chain for demo recording

echo "  → binance ... ✗ timeout (5000ms)"
sleep 0.8
echo "  → coingecko ... ✗ rate limited"
sleep 0.6
echo "  → kraken ... ✓ (142ms)"
echo ""
printf "  %-12s %10s %10s %10s %10s %14s\n" "TIME" "OPEN" "HIGH" "LOW" "CLOSE" "VOLUME"
printf "  %-12s %10s %10s %10s %10s %14s\n" "──────────" "────────" "────────" "────────" "────────" "────────────"
printf "  %-12s %10.2f %10.2f %10.2f %10.2f %14.0f\n" "2026-08-03" 119842.60 121050.80 119200.10 120678.40 51027
printf "  %-12s %10.2f %10.2f %10.2f %10.2f %14.0f\n" "2026-08-04" 120678.40 121890.00 120100.50 121455.20 44812
printf "  %-12s %10.2f %10.2f %10.2f %10.2f %14.0f\n" "2026-08-05" 121455.20 122300.00 121000.00 121890.35 39506
