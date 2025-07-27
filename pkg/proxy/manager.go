package proxy

import (
	"fmt"
	"math/rand"
	"net/http"
	"net/url"
	"sync"
	"time"
)

type ProxyConfig struct {
	Enabled     bool     `json:"enabled"`
	ProxyList   []string `json:"proxyList"`
	RotateEvery int      `json:"rotateEvery"` // Number of requests before rotating
	Timeout     int      `json:"timeout"`     // Timeout in seconds
}

type ProxyManager struct {
	config       ProxyConfig
	proxies      []*url.URL
	currentIndex int
	requestCount int
	mutex        sync.RWMutex
	userAgents   []string
}

func NewProxyManager(config ProxyConfig) (*ProxyManager, error) {
	pm := &ProxyManager{
		config:     config,
		proxies:    make([]*url.URL, 0, len(config.ProxyList)),
		userAgents: getRandomUserAgents(),
	}

	// Parse proxy URLs
	for _, proxyStr := range config.ProxyList {
		proxyURL, err := url.Parse(proxyStr)
		if err != nil {
			return nil, fmt.Errorf("invalid proxy URL %s: %w", proxyStr, err)
		}
		pm.proxies = append(pm.proxies, proxyURL)
	}

	// Shuffle proxies for better distribution
	rand.Shuffle(len(pm.proxies), func(i, j int) {
		pm.proxies[i], pm.proxies[j] = pm.proxies[j], pm.proxies[i]
	})

	return pm, nil
}

func (pm *ProxyManager) GetHTTPClient() *http.Client {
	if !pm.config.Enabled || len(pm.proxies) == 0 {
		return &http.Client{
			Timeout: time.Duration(pm.config.Timeout) * time.Second,
		}
	}

	pm.mutex.Lock()
	defer pm.mutex.Unlock()

	// Rotate proxy if needed
	if pm.config.RotateEvery > 0 && pm.requestCount >= pm.config.RotateEvery {
		pm.currentIndex = (pm.currentIndex + 1) % len(pm.proxies)
		pm.requestCount = 0
	}

	proxy := pm.proxies[pm.currentIndex]
	pm.requestCount++

	transport := &http.Transport{
		Proxy: http.ProxyURL(proxy),
	}

	return &http.Client{
		Transport: transport,
		Timeout:   time.Duration(pm.config.Timeout) * time.Second,
	}
}

func (pm *ProxyManager) GetRandomUserAgent() string {
	if len(pm.userAgents) == 0 {
		return "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
	}

	return pm.userAgents[rand.Intn(len(pm.userAgents))]
}

func (pm *ProxyManager) GetCurrentProxy() string {
	if !pm.config.Enabled || len(pm.proxies) == 0 {
		return "direct"
	}

	pm.mutex.RLock()
	defer pm.mutex.RUnlock()

	return pm.proxies[pm.currentIndex].String()
}

func (pm *ProxyManager) RotateProxy() {
	if !pm.config.Enabled || len(pm.proxies) <= 1 {
		return
	}

	pm.mutex.Lock()
	defer pm.mutex.Unlock()

	pm.currentIndex = (pm.currentIndex + 1) % len(pm.proxies)
	pm.requestCount = 0
}

func (pm *ProxyManager) MarkProxyBad(proxyURL string) {
	if !pm.config.Enabled {
		return
	}

	pm.mutex.Lock()
	defer pm.mutex.Unlock()

	// Remove bad proxy from rotation
	for i, proxy := range pm.proxies {
		if proxy.String() == proxyURL {
			pm.proxies = append(pm.proxies[:i], pm.proxies[i+1:]...)
			if pm.currentIndex >= len(pm.proxies) && len(pm.proxies) > 0 {
				pm.currentIndex = 0
			}
			break
		}
	}
}

func (pm *ProxyManager) TestProxy(proxyURL *url.URL) error {
	transport := &http.Transport{
		Proxy: http.ProxyURL(proxyURL),
	}

	client := &http.Client{
		Transport: transport,
		Timeout:   10 * time.Second,
	}

	// Test with a simple HTTP request
	resp, err := client.Get("http://httpbin.org/ip")
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("proxy test failed with status: %d", resp.StatusCode)
	}

	return nil
}

func (pm *ProxyManager) TestAllProxies() {
	if !pm.config.Enabled {
		return
	}

	var workingProxies []*url.URL

	for _, proxy := range pm.proxies {
		if err := pm.TestProxy(proxy); err == nil {
			workingProxies = append(workingProxies, proxy)
		}
	}

	pm.mutex.Lock()
	pm.proxies = workingProxies
	if pm.currentIndex >= len(pm.proxies) && len(pm.proxies) > 0 {
		pm.currentIndex = 0
	}
	pm.mutex.Unlock()
}

func getRandomUserAgents() []string {
	return []string{
		"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
		"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
		"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
		"Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
		"Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/121.0",
		"Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/121.0",
		"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
		"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
		"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
		"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
	}
}
