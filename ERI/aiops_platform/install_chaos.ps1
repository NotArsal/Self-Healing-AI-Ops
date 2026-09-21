.\helm.exe repo add chaos-mesh https://charts.chaos-mesh.org
.\helm.exe repo update
.\helm.exe upgrade --install chaos-mesh chaos-mesh/chaos-mesh --namespace chaos --set dashboard.create=true
