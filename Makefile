# 🔄 Trigger Blue-Green Failover and Watcher Alert
failover-test:
	@echo "\n🚨 Triggering FAILOVER TEST..."
	@echo "Step 1: Trigger failure on BLUE pool"
	curl -s -X POST http://localhost:8081/chaos/start?mode=error
	sleep 2

	@echo "\nStep 2: Verify failover (should now return X-App-Pool: green)"
	curl -i http://localhost:8080/version | grep X-App-Pool || echo "⚠️ No X-App-Pool header found"

	@echo "\nStep 3: Stop chaos mode"
	curl -s -X POST http://localhost:8081/chaos/stop
	sleep 2

	@echo "\n✅ Failover test completed. Check your Slack channel for alerts!"
