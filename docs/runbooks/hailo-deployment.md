# Hailo-8L Deployment Runbook

Step-by-step checklist for compiling, deploying, and validating neural models
on the Hailo-8L accelerator attached to a Raspberry Pi 5.

---

## Prerequisites Checklist

- [ ] Raspberry Pi 5 (8 GB RAM recommended) with Hailo-8L M.2 HAT installed
- [ ] HailoRT runtime >= 4.17 installed (`hailortcli --version`)
- [ ] Hailo Dataflow Compiler >= 3.27 installed on the build machine
- [ ] Python 3.11+ with `hailo_platform` pip package
- [ ] Trained ONNX models available: `anomaly_lstm.onnx`, `fusion_transformer.onnx`
- [ ] SSH access to the target Pi 5 with `sudo` privileges

---

## Step 1: ONNX to HEF Compilation

Run these commands on the build machine (x86-64 with Dataflow Compiler).

### anomaly_lstm

- [ ] Parse the ONNX model
  ```bash
  hailo parser onnx anomaly_lstm.onnx --net-name anomaly_lstm
  ```
- [ ] Optimize for Hailo-8L
  ```bash
  hailo optimize anomaly_lstm.har --hw-arch hailo8l
  ```
- [ ] Compile to HEF
  ```bash
  hailo compiler anomaly_lstm_optimized.har --hw-arch hailo8l -o anomaly_lstm.hef
  ```
- [ ] Verify HEF integrity
  ```bash
  hailortcli parse-hef anomaly_lstm.hef
  ```

### fusion_transformer

- [ ] Parse the ONNX model
  ```bash
  hailo parser onnx fusion_transformer.onnx --net-name fusion_transformer
  ```
- [ ] Optimize for Hailo-8L
  ```bash
  hailo optimize fusion_transformer.har --hw-arch hailo8l
  ```
- [ ] Compile to HEF
  ```bash
  hailo compiler fusion_transformer_optimized.har --hw-arch hailo8l -o fusion_transformer.hef
  ```
- [ ] Verify HEF integrity
  ```bash
  hailortcli parse-hef fusion_transformer.hef
  ```

---

## Step 2: Runtime Setup on Pi 5

- [ ] Scan for Hailo device
  ```bash
  hailortcli scan
  ```
- [ ] Confirm device firmware matches runtime version
  ```bash
  hailortcli fw-control identify
  ```
- [ ] Configure power mode for sustained inference
  ```bash
  hailortcli fw-control config --power-mode performance
  ```
- [ ] Install Python bindings
  ```bash
  pip install hailo_platform
  ```
- [ ] Copy compiled HEF files to the target directory
  ```bash
  scp anomaly_lstm.hef fusion_transformer.hef pi@<PI_IP>:/opt/tricorder/models/
  ```
- [ ] Verify Python can import the runtime
  ```bash
  python -c "from hailo_platform import HEF, VDevice; print('OK')"
  ```

---

## Step 3: Model Hot-Swap Workflow

Use this procedure to replace a running HEF model with a new version
without a full system restart.

- [ ] Stop the tricorder inference service
  ```bash
  sudo systemctl stop tricorder-inference
  ```
- [ ] Back up the current HEF
  ```bash
  cp /opt/tricorder/models/anomaly_lstm.hef /opt/tricorder/models/anomaly_lstm.hef.bak
  ```
- [ ] Replace with the new HEF
  ```bash
  cp /tmp/anomaly_lstm_v2.hef /opt/tricorder/models/anomaly_lstm.hef
  ```
- [ ] Update `config.yaml` if input/output shapes have changed
  ```bash
  nano /opt/tricorder/config.yaml
  ```
- [ ] Restart the inference service
  ```bash
  sudo systemctl start tricorder-inference
  ```
- [ ] Verify the service is healthy
  ```bash
  sudo systemctl status tricorder-inference
  curl -s http://localhost:8000/health | python -m json.tool
  ```

---

## Step 4: Validation Checklist

- [ ] Inference latency < 10 ms per sample (measure with `time` or built-in profiler)
  ```bash
  python -m tricorder.benchmark --model anomaly_lstm --iterations 1000
  ```
- [ ] Output tensor shape matches expected shape from ONNX baseline
- [ ] Prediction accuracy within 5% of the ONNX CPU baseline
  ```bash
  python -m tricorder.validate --hef anomaly_lstm.hef --onnx anomaly_lstm.onnx --tolerance 0.05
  ```
- [ ] No memory leaks over a 1-hour sustained run
  ```bash
  python -m tricorder.benchmark --model anomaly_lstm --duration 3600 --monitor-memory
  ```
- [ ] Thermal stability: SoC temperature stays below 80 C under load
  ```bash
  watch -n 5 'cat /sys/class/thermal/thermal_zone0/temp'
  ```
- [ ] All unit tests pass with the new HEF in place
  ```bash
  pytest tests/unit/test_hailo_adapter.py -v
  ```
