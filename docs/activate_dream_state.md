# Dream State Activation Guide

## When to Activate
Activate Dream State when:
- You're done with major development
- You want automatic memory optimization
- You're comfortable with nightly token usage (~$0.17/night)

## How to Activate

### Step 1: Enable Timer
```bash
sudo systemctl enable veda-dream.timer
sudo systemctl start veda-dream.timer
```

### Step 2: Verify
```bash
# Check timer status
sudo systemctl list-timers veda-dream

# Should show next run at 2:00 AM IST
```

### Step 3: Monitor First Run
```bash
# Check logs after first run
sudo journalctl -u veda-dream -f
```

## How to Deactivate
```bash
# Stop timer
sudo systemctl stop veda-dream.timer
sudo systemctl disable veda-dream.timer
```

## Manual Test Anytime
```bash
# Run dream state manually
cd ~/veda
uv run python scripts/dream_state.py

# Check what it did
sudo journalctl -u veda-dream -n 100
```

## Budget Impact
- Runs once per day at 2 AM
- Uses ~$0.17/day (Kimi K2.5 model)
- Annual cost: ~$62/year for dream state
