 cd /media/oitech/KINGSTON/EIS_ENV_INSTALL
 sudo ./install_eis_complete.sh


 
 
完整安装：
sudo bash install_eis_complete.sh

安装脚本会自动配置下位机EIS通信网卡：
- 下位机静态地址：192.168.98.3/24
- EIS服务器地址：192.168.98.2
- 不设置默认网关，不影响其他网卡上网
- 配置会在开关机后保持生效

只配置网络：
sudo bash setup_static_network.sh

指定网卡或修改地址：
sudo EIS_NETWORK_INTERFACE=eth1 EIS_STATIC_CIDR=192.168.98.3/24 EIS_SERVER_IP=192.168.98.2 bash setup_static_network.sh

总安装时跳过网络配置：
sudo EIS_SKIP_NETWORK_SETUP=1 bash install_eis_complete.sh
