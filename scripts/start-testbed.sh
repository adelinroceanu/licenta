#!/bin/bash
# Pornire completă testbed 5G după reboot
# Usage: ./start-testbed.sh

set -e

WIFI_IFACE="wlp4s0"  # ajustează dacă e altul
PROJECT_DIR="$HOME/licenta"
UERANSIM_DIR="$HOME/UERANSIM"

echo "=== 1. Verifică Open5GS ==="
sudo systemctl status open5gs-amfd | grep Active
sudo systemctl status open5gs-smfd | grep Active
sudo systemctl status open5gs-upfd | grep Active

echo ""
echo "=== 2. Configurez NAT pentru tunelul 5G ==="
sudo sysctl -w net.ipv4.ip_forward=1
sudo iptables -t nat -C POSTROUTING -s 10.45.0.0/16 -o $WIFI_IFACE -j MASQUERADE 2>/dev/null || \
    sudo iptables -t nat -A POSTROUTING -s 10.45.0.0/16 -o $WIFI_IFACE -j MASQUERADE
sudo iptables -C FORWARD -i ogstun -o $WIFI_IFACE -j ACCEPT 2>/dev/null || \
    sudo iptables -A FORWARD -i ogstun -o $WIFI_IFACE -j ACCEPT
sudo iptables -C FORWARD -i $WIFI_IFACE -o ogstun -m state --state RELATED,ESTABLISHED -j ACCEPT 2>/dev/null || \
    sudo iptables -A FORWARD -i $WIFI_IFACE -o ogstun -m state --state RELATED,ESTABLISHED -j ACCEPT

echo ""
echo "=== 3. Verifică cluster Kubernetes ==="
kubectl get nodes

echo ""
echo "=== 4. Pornesc port-forward-uri (în background) ==="
pkill -f "port-forward.*nf-stubs" 2>/dev/null
sleep 1
kubectl port-forward -n nf-stubs svc/amf-stub 18080:8080 > /tmp/pf-amf.log 2>&1 &
kubectl port-forward -n nf-stubs svc/smf-stub 18081:8080 > /tmp/pf-smf.log 2>&1 &
kubectl port-forward -n nf-stubs svc/upf-stub 18082:8080 > /tmp/pf-upf.log 2>&1 &
sleep 2
echo "Port-forward-uri pornite (PID-uri: $(pgrep -f 'port-forward.*nf-stubs' | tr '\n' ' '))"

echo ""
echo "=== 5. Test conectivitate stub-uri ==="
curl -s http://localhost:18080/healthz && echo " ← AMF stub OK"
curl -s http://localhost:18081/healthz && echo " ← SMF stub OK"
curl -s http://localhost:18082/healthz && echo " ← UPF stub OK"

echo ""
echo "=== 6. Pornesc conector în background ==="
pkill -f "connector.py" 2>/dev/null
sleep 1
nohup python3 $PROJECT_DIR/connector/connector.py > /tmp/connector.log 2>&1 &
echo "Conector pornit (PID: $!)"

echo ""
echo "=== Setup gata! ==="
echo ""
echo "Pentru a porni gNB și UE, deschide 2 terminale separate și rulează:"
echo "  Terminal 1: cd $UERANSIM_DIR && ./build/nr-gnb -c config-licenta/gnb.yaml"
echo "  Terminal 2: cd $UERANSIM_DIR && sudo ./build/nr-ue -c config-licenta/ue.yaml"
echo ""
echo "Pentru a vedea log-urile conectorului: tail -f /tmp/connector.log"
echo "Pentru a accesa Grafana: http://localhost:30030 (admin/admin123)"
echo "Pentru a accesa Prometheus: kubectl port-forward -n monitoring svc/monitoring-kube-prometheus-prometheus 19090:9090 &"
