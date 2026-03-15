# Kubernetes 部署

本目录为 NanoClaw 在 Kubernetes 上的示例清单，使用前请阅读：

**详细步骤与说明**：[../docs/K8S_DEPLOYMENT_ZH.md](../docs/K8S_DEPLOYMENT_ZH.md)

## 快速部署顺序

```bash
kubectl apply -f namespace.yaml
kubectl apply -f pvc.yaml
kubectl apply -f configmap.yaml
# 创建 Secret（勿提交 secret.yaml）
kubectl create secret generic nanoclaw-secret --from-env-file=.env -n nanoclaw --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml
```

## 文件说明

| 文件 | 说明 |
|------|------|
| namespace.yaml | 命名空间 |
| pvc.yaml | 持久化存储 |
| configmap.yaml | 非敏感配置 |
| secret.example.yaml | Secret 示例（复制并填入真实值，另存为 secret.yaml，且不要提交） |
| deployment.yaml | Host Deployment（挂载 Docker 套接字、PVC，注入 Pod IP） |
| service.yaml | Service |
