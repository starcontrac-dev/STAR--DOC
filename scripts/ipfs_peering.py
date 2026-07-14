import os
import subprocess
import json
import argparse
from typing import List

def run_ipfs_command(args: List[str]) -> str:
    """Ejecuta un comando de la CLI de IPFS y retorna la salida."""
    try:
        result = subprocess.run(
            ['ipfs'] + args,
            check=True,
            capture_output=True,
            text=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"❌ Error ejecutando ipfs {' '.join(args)}: {e.stderr}")
        return ""
    except FileNotFoundError:
        print("❌ Error: No se encontró el comando 'ipfs'. Asegúrate de que Kubo está instalado y en el PATH.")
        exit(1)

def add_to_peering_config(peer_id: str, multiaddrs: List[str]):
    """Agrega un Peer permanentemente a la configuración de Peering."""
    print(f"🔧 Configurando Peering permanente para el nodo: {peer_id}")
    
    # 1. Obtener la configuración actual de Peering
    peering_config_str = run_ipfs_command(['config', 'Peering'])
    
    peering_config = {"Peers": []}
    if peering_config_str and peering_config_str != "null":
        peering_config = json.loads(peering_config_str)
        if not peering_config.get("Peers"):
             peering_config["Peers"] = []
             
    # 2. Verificar si ya existe
    for peer in peering_config["Peers"]:
        if peer.get("ID") == peer_id:
            print(f"✅ El Peer {peer_id} ya existe en tu configuración de Peering.")
            return

    # 3. Agregar el nuevo peer
    peering_config["Peers"].append({
        "ID": peer_id,
        "Addrs": multiaddrs
    })
    
    # 4. Guardar la configuración temporalmente y aplicarla
    temp_file = "temp_peering.json"
    with open(temp_file, "w") as f:
        json.dump(peering_config, f)
        
    try:
        run_ipfs_command(['config', 'Peering', '--json', open(temp_file).read()])
        print(f"✅ Peer configurado exitosamente en el archivo de configuración.")
        print("💡 Para que los cambios surtan efecto por completo, debes reiniciar el demonio de IPFS.")
    finally:
        if os.path.exists(temp_file):
            os.remove(temp_file)

def connect_swarm(multiaddr: str):
    """Intenta conectar al Swarm inmediatamente."""
    print(f"🔗 Intentando conexión directa vía Swarm a {multiaddr}...")
    output = run_ipfs_command(['swarm', 'connect', multiaddr])
    if output:
        print(f"✅ Resultado: {output}")

def main():
    print("===============================================")
    print("🌐 STAR-DOC: Gestor de Conexión de Pares IPFS")
    print("===============================================")
    
    parser = argparse.ArgumentParser(description="Conecta este nodo local a un nodo IPFS remoto.")
    parser.add_argument("--peer-id", type=str, required=True, help="El ID del Peer remoto (ej: 12D3Koo...)")
    parser.add_argument("--ip", type=str, default="192.168.1.X", help="Dirección IP de la máquina remota en la red local.")
    parser.add_argument("--port", type=str, default="4001", help="Puerto Swarm del nodo remoto (por defecto 4001).")
    
    args = parser.parse_args()
    
    # Construir el Multiaddr
    # Un multiaddr típico de red local se ve así: /ip4/192.168.1.100/tcp/4001/p2p/12D3Koo...
    multiaddr = f"/ip4/{args.ip}/tcp/{args.port}/p2p/{args.peer_id}"
    print(f"📍 Multiaddr objetivo: {multiaddr}")
    
    # Conectar y guardar
    connect_swarm(multiaddr)
    add_to_peering_config(args.peer_id, [f"/ip4/{args.ip}/tcp/{args.port}"])
    
if __name__ == "__main__":
    main()
