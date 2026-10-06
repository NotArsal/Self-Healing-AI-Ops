# OpenRCA ops-lite 5-Case Validation Report

## Summary
- **F02 Top-1 Accuracy**: 100.0% (2/2)
- **Mapped/Unmapped Coverage**: 2 Mapped / 3 Unmapped
- **Average RCA Latency**: 2008ms

## Case Breakdown

### Case: hs0-attractions-pod-failure-s8fsgm
- **Actual Chaos Type**: PodFailure
- **Mapped Status**: UNMAPPED
- **Affected Service**: attractions
- **Predicted Fault**: F02
- **Pass/Fail**: FAIL
- **Latency**: 5208ms
- **Extracted Metrics**: frontend_error, frontend_latency-50, search_latency-50, reservation_latency-50, reservation_latency-90
- **Extracted Logs**: 3

### Case: hs1-frontend-delay-24srn4
- **Actual Chaos Type**: NetworkDelay
- **Mapped Status**: F02
- **Affected Service**: frontend
- **Predicted Fault**: F02
- **Pass/Fail**: PASS
- **Latency**: 1202ms
- **Extracted Metrics**: frontend_latency-90, search_latency-90, profile_latency-90, reservation_latency-90, reservation_latency-50
- **Extracted Logs**: 3

### Case: hs1-geo-cpu-exhaustion-q8nln6
- **Actual Chaos Type**: CPUStress
- **Mapped Status**: UNMAPPED
- **Affected Service**: geo
- **Predicted Fault**: F02
- **Pass/Fail**: FAIL
- **Latency**: 1121ms
- **Extracted Metrics**: search_latency-90, frontend_latency-90, reservation_latency-90, reservation_latency-50, attractions_latency-90
- **Extracted Logs**: 3

### Case: ts0-ts-travel-plan-service-response-delay-pfwcqk
- **Actual Chaos Type**: HTTPResponseDelay
- **Mapped Status**: F02
- **Affected Service**: ts-travel-plan-service
- **Predicted Fault**: F02
- **Pass/Fail**: PASS
- **Latency**: 1298ms
- **Extracted Metrics**: ts-travel-plan-service_latency-50, ts-travel-plan-service_latency-90, ts-route-plan-service_latency-50, ts-travel-plan-service_error, ts-preserve-service_latency-90
- **Extracted Logs**: 3

### Case: ts0-ts-travel-plan-service-response-replace-code-7ps8tm
- **Actual Chaos Type**: HTTPResponseReplaceCode
- **Mapped Status**: UNMAPPED
- **Affected Service**: ts-travel-plan-service
- **Predicted Fault**: F02
- **Pass/Fail**: FAIL
- **Latency**: 1210ms
- **Extracted Metrics**: ts-travel-plan-service_error, ts-travel-plan-service_latency-50, ts-ui-dashboard_error, ts-preserve-service_latency-90, ts-travel-service_latency-90
- **Extracted Logs**: 3

