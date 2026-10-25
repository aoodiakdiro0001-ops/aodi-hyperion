// Aodı-Hyperion — signed gossip mesh daemon (stdlib only).
//
// Discovery + authenticity in one layer:
//   - each node holds a persistent ECDSA P-256 identity key
//   - /hy/mesh/state is a SIGNED snapshot: (name, ts, tags, load) + sig
//   - heartbeats verify the peer signature on every round; unverified
//     snapshots NEVER touch the node table (report honestly instead)
//     Honest scope: post-quantum (Kyber/Dilithiumstyle) signing has no stdlib
//     implementation; the protocol keeps a slot for it (see docs/WHITEPAPER.md).
package main

import (
	"bytes"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/sha256"
	"crypto/x509"
	"encoding/base64"
	"encoding/json"
	"encoding/pem"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"time"
)

const version = "1.0.0"
const httpTimeout = 3 * time.Second

var (
	mu      sync.RWMutex
	peers   = map[string]*peer{} // url → peer
	priv    *ecdsa.PrivateKey
	pubDER  []byte
	started = time.Now()
	hbEvery = 10 * time.Second
)

type peer struct {
	URL      string   `json:"url"`
	Name     string   `json:"name"`
	Tags     []string `json:"tags"`
	Load     float64  `json:"load"`
	Up       bool     `json:"up"`
	Misses   int      `json:"-"`
	YDER     string   `json:"pubkey"`   // base64 DER SPKI
	Verified int      `json:"verified"` // verified handshakes count
	Seen     string   `json:"last_seen"`
}

type signedState struct {
	Name string   `json:"name"`
	TS   int64    `json:"ts"`
	Tags []string `json:"tags"`
	Load float64  `json:"load"`
	Pub  string   `json:"pubkey"`
	Sig  string   `json:"sig"`
}

func getenv(k, d string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return d
}

func tagsCSV(s string) []string {
	if s == "" {
		return []string{"lite"}
	}
	var out []string
	for _, p := range strings.Split(s, ",") {
		if p = strings.TrimSpace(p); p != "" {
			out = append(out, p)
		}
	}
	return out
}

func payloadOf(s signedState) []byte {
	raw, _ := json.Marshal([]any{s.Name, s.TS, s.Tags, s.Load, s.Pub})
	return raw
}

func signState() signedState {
	st := signedState{
		Name: getenv("HY_NAME", hostname()),
		TS:   time.Now().UTC().Unix(),
		Tags: tagsCSV(getenv("HY_TAGS", "lite,gpu")),
		Load: 0.0,
		Pub:  base64.StdEncoding.EncodeToString(pubDER),
	}
	hashed := sha256.Sum256(payloadOf(st))
	sig, _ := ecdsa.SignASN1(rand.Reader, priv, hashed[:])
	st.Sig = base64.StdEncoding.EncodeToString(sig)
	return st
}

func verifyState(st signedState) bool {
	if st.Pub == "" || st.Sig == "" {
		return false
	}
	der, err := base64.StdEncoding.DecodeString(st.Pub)
	if err != nil {
		return false
	}
	pubAny, err := x509.ParsePKIXPublicKey(der)
	if err != nil {
		return false
	}
	pub, ok := pubAny.(*ecdsa.PublicKey)
	if !ok || pub.Curve != elliptic.P256() {
		return false
	}
	sig, err := base64.StdEncoding.DecodeString(st.Sig)
	if err != nil {
		return false
	}
	hashed := sha256.Sum256(payloadOf(signedState{
		Name: st.Name, TS: st.TS, Tags: st.Tags, Load: st.Load, Pub: st.Pub,
	}))
	return ecdsa.VerifyASN1(pub, hashed[:], sig)
}

// ---------- HTTP surface ----------
func writeJSON(w http.ResponseWriter, code int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Access-Control-Allow-Origin", "*")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(v)
}

func stateHandler(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, 200, signedSnapshot())
}

func signedSnapshot() signedState {
	return signState()
}

func nodesHandler(w http.ResponseWriter, r *http.Request) {
	mu.RLock()
	defer mu.RUnlock()
	list := make([]map[string]any, 0, len(peers))
	for _, p := range peers {
		list = append(list, map[string]any{
			"name": p.Name, "url": p.URL, "up": p.Up, "load": p.Load,
			"tags": p.Tags, "pubkey": p.YDER, "verified": p.Verified,
			"last_seen": p.Seen,
		})
	}
	writeJSON(w, 200, map[string]any{"nodes": list})
}

func peersHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method == http.MethodPost {
		var in struct {
			Peers []string `json:"peers"`
		}
		body, _ := io.ReadAll(io.LimitReader(r.Body, 1<<20))
		if err := json.Unmarshal(body, &in); err != nil {
			writeJSON(w, 400, map[string]string{"error": "bad json"})
			return
		}
		mu.Lock()
		for _, u := range in.Peers {
			u = strings.TrimSpace(u)
			if u == "" || !strings.HasPrefix(u, "http") {
				continue
			}
			if _, ok := peers[u]; !ok {
				peers[u] = &peer{URL: u}
			}
		}
		mu.Unlock()
		writeJSON(w, 200, map[string]any{"ok": true, "count": len(peers)})
		return
	}
	mu.RLock()
	defer mu.RUnlock()
	urls := make([]string, 0, len(peers))
	for u := range peers {
		urls = append(urls, u)
	}
	writeJSON(w, 200, map[string]any{"peers": urls})
}

func healthHandler(w http.ResponseWriter, r *http.Request) {
	mu.RLock()
	up, verified := 0, 0
	for _, p := range peers {
		if p.Up {
			up++
		}
		if p.Verified > 0 {
			verified++
		}
	}
	mu.RUnlock()
	writeJSON(w, 200, map[string]any{
		"service": "hyperion.mesh", "version": version,
		"uptime_seconds": int(time.Since(started).Seconds()),
		"peers_known":    len(peers), "peers_up": up,
		"peers_verified": verified, "signing": "ecdsa-p256",
		"heartbeat_s": int(hbEvery.Seconds()),
	})
}

// ---------- heartbeat (verify on every round) ----------
func heartbeatOnce() {
	mu.RLock()
	urls := make([]string, 0, len(peers))
	for u := range peers {
		urls = append(urls, u)
	}
	mu.RUnlock()

	client := &http.Client{Timeout: httpTimeout}
	var wg sync.WaitGroup
	for _, u := range urls {
		wg.Add(1)
		go func(raw string) {
			defer wg.Done()
			resp, err := client.Get(strings.TrimSuffix(raw, "/") + "/hy/mesh/state")
			mu.Lock()
			defer mu.Unlock()
			p := peers[raw]
			if p == nil {
				return
			}
			if err != nil {
				p.Misses++
				if p.Misses >= 3 {
					p.Up = false
				}
				return
			}
			body, err := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
			resp.Body.Close()
			if err != nil || resp.StatusCode != http.StatusOK {
				p.Misses++
				if p.Misses >= 3 {
					p.Up = false
				}
				return
			}
			var st signedState
			if err := json.Unmarshal(body, &st); err != nil ||
				!verifyState(st) {
				// signed-and-failed: never ingest an unverified snapshot
				p.Misses++
				return
			}
			p.Name = st.Name
			p.Load = st.Load
			p.Tags = st.Tags
			p.YDER = st.Pub
			p.Up, p.Misses = true, 0
			p.Verified++
			p.Seen = time.Now().UTC().Format(time.RFC3339)
		}(u)
	}
	wg.Wait()
}

func heartbeatLoop() {
	for {
		heartbeatOnce()
		time.Sleep(hbEvery)
	}
}

// ---------- identity key persistence ----------
func loadOrCreateKey(dir string) {
	pub, privPath := filepath.Join(dir, "gossip.pub.pem"),
		filepath.Join(dir, "gossip.key.pem")
	if data, err := os.ReadFile(privPath); err == nil {
		block, _ := pem.Decode(data)
		if k, e := x509.ParseECPrivateKey(block.Bytes); e == nil {
			priv = k
			pubDER, _ = x509.MarshalPKIXPublicKey(&k.PublicKey)
			return
		}
	}
	k, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		panic(err)
	}
	priv = k
	pubDER, _ = x509.MarshalPKIXPublicKey(&k.PublicKey)
	_ = os.MkdirAll(dir, 0o755)
	keyDER, _ := x509.MarshalECPrivateKey(k)
	_ = os.WriteFile(privPath, pem.EncodeToMemory(&pem.Block{
		Type: "EC PRIVATE KEY", Bytes: keyDER}), 0o600)
	pubPEM, _ := x509.MarshalPKIXPublicKey(&k.PublicKey)
	_ = os.WriteFile(pub, pem.EncodeToMemory(&pem.Block{
		Type: "PUBLIC KEY", Bytes: pubPEM}), 0o644)
}

func hostname() string {
	h, err := os.Hostname()
	if err != nil {
		return "mesh-local"
	}
	return h
}

func main() {
	loadOrCreateKey(getenv("HY_KEY_DIR", "."))
	if so := os.Getenv("HY_HEARTBEAT_S"); so != "" {
		if n, err := strconv.Atoi(so); err == nil && n > 0 && n <= 300 {
			hbEvery = time.Duration(n) * time.Second
		}
	}
	if seeds := os.Getenv("HY_PEERS"); seeds != "" {
		var list []string
		for _, s := range strings.Split(seeds, ",") {
			if s = strings.TrimSpace(s); s != "" {
				list = append(list, s)
			}
		}
		go func() {
			time.Sleep(500 * time.Millisecond)
			body, _ := json.Marshal(map[string]any{"peers": list})
			req, err := http.NewRequest(http.MethodPost,
				"http://127.0.0.1"+getenv("HY_ADDR", ":9411")+
					"/hy/mesh/peers", bytes.NewReader(body))
			if err == nil {
				client := &http.Client{Timeout: 2 * time.Second}
				_, _ = client.Do(req)
			}
		}()
	}
	go heartbeatLoop()

	mux := http.NewServeMux()
	mux.HandleFunc("/hy/mesh/state", stateHandler)
	mux.HandleFunc("/hy/mesh/nodes", nodesHandler)
	mux.HandleFunc("/hy/mesh/peers", peersHandler)
	mux.HandleFunc("/hy/mesh/health", healthHandler)

	addr := getenv("HY_ADDR", ":9411")
	srv := &http.Server{Addr: addr, Handler: mux,
		ReadHeaderTimeout: 5 * time.Second, WriteTimeout: 10 * time.Second}
	fmt.Println("Aodı-Hyperion mesh v"+version, "listening on", addr,
		"signing: ecdsa-p256")
	_ = srv.ListenAndServe()
}
