.PHONY: mesh core tests clean

mesh:            ## build signed gossip daemon
	cd mesh && gofmt -w . && go vet ./... && go build -o ../bin/hy-mesh .

core:            ## organism API + dashboard on :9412
	python3 core/server.py --port 9412

tests:           ## offline battery
	python3 tests/test_hyperion.py -v
	node --check relay/relay.js

zk-selftest:     ## prove/verify roundtrip on the real group
	python3 core/zk.py

evolve-demo:     ## recorded genetic run
	python3 core/cli.py evolve 3 5
