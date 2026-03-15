# NanoClaw 部署到 Kubernetes 操作指南

本文说明如何将 NanoClaw 部署到 Kubernetes，包括镜像构建、持久化、凭证代理可达性、Docker 套接字挂载及常见限制与替代方案。

---

## 一、架构要点

- **Host 进程**：单 Node 进程，负责渠道、消息轮询、群组队列、计划任务、IPC、凭证代理；需在集群内以 **Deployment** 形式常驻。
- **Agent 容器**：由 Host 通过 **Docker（或 containerd）** 在**同一节点**上 `docker run` 启动，每个群组独立容器；容器内需能访问 Host 上的 **Credential Proxy**（端口 3001）。
- **K8s 下的难点**：Host 跑在 Pod 内，Agent 容器由该 Pod 通过节点上的 Docker 套接字启动；Agent 内使用的 `host.docker.internal` 在节点上指向**节点 IP**，而 Credential Proxy 在 **Pod IP**。因此需通过环境变量 **`CONTAINER_HOST_GATEWAY_IP`** 将 Pod IP 注入，使 Agent 解析 `host.docker.internal` 时指向 NanoClaw Pod，从而访问凭证代理。

本仓库已支持 **`CONTAINER_HOST_GATEWAY_IP`**（见 `src/container-runtime.ts`）：在 K8s 中通过 Downward API 将 `status.podIP` 注入即可。

---

## 二、前置条件

| 条件 | 说明 |
|------|------|
| 集群可访问 | `kubectl` 已配置且能访问目标集群 |
| 节点含 Docker 套接字 | 需挂载 `/var/run/docker.sock`，即节点上需运行 Docker；**使用 containerd 且无 Docker 的节点需另案处理**（见下文替代方案） |
| 镜像可被节点拉取 | Host 镜像（如 `nanoclaw-host:latest`）与 Agent 镜像（如 `nanoclaw-agent:latest`）需推送到集群可访问的镜像仓库，或使用本地镜像（需各节点已拉取） |
| 持久化存储 | 为 store（SQLite）、data（sessions、ipc）、logs 准备 PVC |

---

## 三、镜像构建

### 3.1 Agent 镜像（供 Host 在容器内 `docker run` 使用）

与本地 Docker 用法一致，在项目根目录执行：

```bash
cd container
./build.sh
# 得到 nanoclaw-agent:latest
```

若部署到集群，需推送到私有仓库，例如：

```bash
docker tag nanoclaw-agent:latest <your-registry>/nanoclaw-agent:latest
docker push <your-registry>/nanoclaw-agent:latest
```

在 K8s 的 Deployment 中通过环境变量指定：

```yaml
env:
  - name: CONTAINER_IMAGE
    value: "<your-registry>/nanoclaw-agent:latest"
```

### 3.2 Host 镜像（K8s Deployment 使用的进程镜像）

Host 镜像需包含：Node 运行时、依赖、构建后的 `dist/`、`container/skills/`、`groups/` 等。

在**项目根目录**执行（先构建再打镜像）：

```bash
npm run build
docker build -f container/Dockerfile.host -t nanoclaw-host:latest .
```

推送至仓库（示例）：

```bash
docker tag nanoclaw-host:latest <your-registry>/nanoclaw-host:latest
docker push <your-registry>/nanoclaw-host:latest
```

Deployment 中 `image` 改为该地址，例如：

```yaml
containers:
  - name: nanoclaw
    image: <your-registry>/nanoclaw-host:latest
```

---

## 四、清单文件说明与部署顺序

`k8s/` 目录下提供示例清单（需按实际集群调整）：

| 文件 | 说明 |
|------|------|
| `namespace.yaml` | 命名空间 `nanoclaw` |
| `pvc.yaml` | 持久化存储，挂载到 store、data、logs |
| `configmap.yaml` | 非敏感配置（ASSISTANT_NAME、CONTAINER_RUNTIME、端口、飞书 App ID 等） |
| `secret.example.yaml` | 敏感项示例；实际 Secret 需自行创建，勿提交 |
| `deployment.yaml` | NanoClaw Host Deployment（挂载 PVC、Docker 套接字、Downward API 注入 Pod IP） |
| `service.yaml` | Service，暴露 3001（凭证代理）、3000（可选 HTTP） |

**部署顺序：**

```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/pvc.yaml
kubectl apply -f k8s/configmap.yaml

# Secret 从本地 .env 生成（勿提交 secret.yaml）
kubectl create secret generic nanoclaw-secret --from-env-file=.env -n nanoclaw --dry-run=client -o yaml | kubectl apply -f -

kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
```

按需修改：

- **configmap.yaml**：`ANTHROPIC_BASE_URL`、`FEISHU_APP_ID`、`MAX_CONCURRENT_CONTAINERS` 等。
- **pvc.yaml**：`storageClassName`、`storage` 大小。
- **deployment.yaml**：`image`、`CONTAINER_IMAGE`（Agent 镜像）、资源 requests/limits、`nodeSelector`（若需固定到带 Docker 的节点）。

---

## 五、关键配置说明

### 5.1 让 Agent 容器访问 Host 上的凭证代理

- Deployment 中已通过 **Downward API** 注入 Pod IP：
  ```yaml
  - name: CONTAINER_HOST_GATEWAY_IP
    valueFrom:
      fieldRef:
        fieldPath: status.podIP
  ```
- Host 进程内使用 **`CREDENTIAL_PROXY_HOST=0.0.0.0`**，使凭证代理监听所有接口，便于同节点上的 Agent 容器通过 Pod IP 访问。

代码中若设置了 **`CONTAINER_HOST_GATEWAY_IP`**，会使用 `--add-host=host.docker.internal:<Pod IP>` 启动 Agent 容器，因此 Agent 内请求 `http://host.docker.internal:3001` 会到达 NanoClaw Pod 的 3001 端口。

### 5.2 挂载 Docker 套接字

```yaml
volumeMounts:
  - name: docker-sock
    mountPath: /var/run/docker.sock
volumes:
  - name: docker-sock
    hostPath:
      path: /var/run/docker.sock
      type: Socket
```

这样 Pod 内可执行 `docker run`，启动的容器会落在**该节点**上。若集群节点仅为 containerd、无 Docker，则需改用下文「替代方案」。

### 5.3 持久化目录

- **store/**：SQLite（messages.db）、状态等。
- **data/**：sessions、ipc 等。
- **logs/**：日志输出。

上述目录通过 PVC 的 `subPath` 挂载到 `/app/store`、`/app/data`、`/app/logs`。**groups/** 当前使用镜像内内容（main、global 等），运行时新建的群组目录在重启后会丢失；若需持久化 groups，可再为 groups 增加 PVC 挂载并在 init 容器中准备默认结构。

---

## 六、验证与排查

- 查看 Pod 与 PVC：
  ```bash
  kubectl get pods -n nanoclaw
  kubectl get pvc -n nanoclaw
  ```
- 查看 Host 日志：
  ```bash
  kubectl logs -f deployment/nanoclaw -n nanoclaw
  ```
- 进入 Pod 排查：
  ```bash
  kubectl exec -it deployment/nanoclaw -n nanoclaw -- sh
  # 检查 /app/store、/app/data、/app/logs 是否有数据
  # 检查是否可访问 /var/run/docker.sock：docker ps
  ```

若 Agent 容器无法访问凭证代理，可检查：

- Pod 内环境变量 `CONTAINER_HOST_GATEWAY_IP` 是否为当前 Pod IP。
- 同节点上启动的 Agent 容器内执行 `curl -s http://host.docker.internal:3001`（或该 Pod IP:3001）是否可达。

---

## 七、无 Docker 套接字时的替代思路

部分集群仅提供 containerd/CRI，且不暴露 Docker 套接字，可采用：

1. **仅允许带 Docker 的节点**  
   为节点打 label，Deployment 使用 `nodeSelector` 或 affinity，只调度到提供 `/var/run/docker.sock` 的节点。

2. **使用 containerd 的 nerdctl 或 CRI**  
   需修改 Host 代码：将当前通过 `docker` 命令/套接字启动容器的逻辑，改为通过 nerdctl 或 Kubernetes API 创建 Pod/Job 来跑 Agent。此为较大改动，需单独设计与实现。

3. **Agent 以 K8s Job 形式运行**  
   Host 不再在节点上 `docker run`，而是通过 Kubernetes API 为每次对话/任务创建 Job（或 Pod），Job 内运行 Agent 镜像，并通过环境变量或 Service 将 Credential Proxy 地址传入。同样需要改代码与部署方式。

当前文档与清单以「节点提供 Docker 套接字」为前提；若采用 2 或 3，需在架构上单独规划。

---

## 八、对外暴露（可选）

- 仅集群内访问：使用 `Service`（如 `nanoclaw.nanoclaw.svc.cluster.local:3001`）即可。
- 对外暴露飞书等回调或管理端点时，可配合 **Ingress** 或 **LoadBalancer** 暴露 Service 的 3000/3001，并配置 TLS 与访问控制。飞书若使用长连接模式则无需公网 Webhook URL。

---

## 九、小结

| 步骤 | 操作 |
|------|------|
| 1 | 构建并推送 `nanoclaw-agent`、`nanoclaw-host` 镜像 |
| 2 | 创建 namespace、PVC、ConfigMap、Secret |
| 3 | 部署 Deployment（挂载 PVC、Docker 套接字，注入 `CONTAINER_HOST_GATEWAY_IP`）与 Service |
| 4 | 确认 Host 日志正常、同节点 Agent 能访问 Pod:3001 |

按上述步骤即可在 Kubernetes 上运行 NanoClaw；若集群无法提供 Docker 套接字，需按「无 Docker 套接字时的替代思路」调整架构与实现。
