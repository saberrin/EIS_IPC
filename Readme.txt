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

运行系统：
bash EIS_Online/run_eis.sh

当前运行入口为 can_tester.py。每次扫频数据成功写入 SQLite 后，系统会在独立线程中自动上传到服务器。
上传地址、超时和重试次数在 EIS_Online/test_command.json 的 upload_config 中配置。

CAN 响应接收：
- 按旧版逻辑连续拼接接收帧，遇到 < 后返回当前响应。
- 不使用按仲裁 ID 分组、半包超时丢弃或响应头强校验。

板卡地址映射：
- EIS_Online/address_mapping.json 只定义板卡所属的 Container/Cluster/Pack。
- Pack 内 Cell 编号使用板卡 GETE 响应头中的 Cell_ID，不再在 address_mapping.json 中固定。

Python 工程结构：
- EIS_Online/can_tester.py：系统运行入口与扫频任务编排。
- EIS_Online/acquisition/：CAN 板卡通信和 EIS 数据采集。
- EIS_Online/database/：SQLite 初始化、数据实体和数据访问。
- EIS_Online/transport/：采集数据上传服务器。
- EIS_Online/tools/：不参与主流程的人工维护工具。
- tests/：自动化回归测试。

手动生成待上传模拟数据：
cd EIS_Online
python -m tools.generate_lower_machine_container_raw_eis
