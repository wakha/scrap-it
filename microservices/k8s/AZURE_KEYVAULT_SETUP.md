# Azure Key Vault Integration for AKS

This guide shows how to integrate Azure Key Vault with your AKS deployment for secure secret management.

## Prerequisites

- Azure CLI installed
- kubectl configured for your AKS cluster
- Azure Key Vault created
- Workload Identity or Pod Identity enabled on AKS

## Option 1: Azure Key Vault Secrets Provider (Recommended)

### Step 1: Enable Azure Key Vault Provider for Secrets Store CSI Driver

```bash
# Set variables
RESOURCE_GROUP="scraper-microservices-rg"
AKS_CLUSTER="scraper-aks-cluster"
KEY_VAULT_NAME="scraper-kv-$(openssl rand -hex 4)"
LOCATION="eastus"

# Enable the addon
az aks enable-addons \
  --addons azure-keyvault-secrets-provider \
  --name $AKS_CLUSTER \
  --resource-group $RESOURCE_GROUP
```

### Step 2: Create Azure Key Vault

```bash
# Create Key Vault
az keyvault create \
  --name $KEY_VAULT_NAME \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION

# Get Key Vault ID
KEY_VAULT_ID=$(az keyvault show --name $KEY_VAULT_NAME --query id -o tsv)
```

### Step 3: Store Secrets in Key Vault

```bash
# Database secrets
az keyvault secret set --vault-name $KEY_VAULT_NAME --name db-password --value "your-secure-password"
az keyvault secret set --vault-name $KEY_VAULT_NAME --name db-user --value "scraper"
az keyvault secret set --vault-name $KEY_VAULT_NAME --name db-name --value "scraper_db"

# API Key
az keyvault secret set --vault-name $KEY_VAULT_NAME --name api-key --value "production-api-key-$(openssl rand -hex 16)"

# Kafka bootstrap servers (if needed)
az keyvault secret set --vault-name $KEY_VAULT_NAME --name kafka-bootstrap-servers --value "kafka:9092"
```

### Step 4: Configure Workload Identity

```bash
# Get AKS OIDC issuer
OIDC_ISSUER=$(az aks show --resource-group $RESOURCE_GROUP --name $AKS_CLUSTER --query "oidcIssuerProfile.issuerUrl" -o tsv)

# Create managed identity
IDENTITY_NAME="scraper-keyvault-identity"
az identity create \
  --name $IDENTITY_NAME \
  --resource-group $RESOURCE_GROUP

# Get identity details
IDENTITY_CLIENT_ID=$(az identity show --name $IDENTITY_NAME --resource-group $RESOURCE_GROUP --query clientId -o tsv)
IDENTITY_PRINCIPAL_ID=$(az identity show --name $IDENTITY_NAME --resource-group $RESOURCE_GROUP --query principalId -o tsv)

# Grant access to Key Vault
az keyvault set-policy \
  --name $KEY_VAULT_NAME \
  --object-id $IDENTITY_PRINCIPAL_ID \
  --secret-permissions get list
```

### Step 5: Create Federated Identity Credential

```bash
# Create federated credential for the service account
az identity federated-credential create \
  --name scraper-federated-identity \
  --identity-name $IDENTITY_NAME \
  --resource-group $RESOURCE_GROUP \
  --issuer $OIDC_ISSUER \
  --subject system:serviceaccount:scraper-microservices:scraper-sa
```

### Step 6: Apply Kubernetes Manifests

See `k8s/azure-keyvault-integration.yaml` for the complete configuration.

```bash
# Update with your values
sed -i "s/<KEY_VAULT_NAME>/$KEY_VAULT_NAME/g" k8s/azure-keyvault-integration.yaml
sed -i "s/<TENANT_ID>/$(az account show --query tenantId -o tsv)/g" k8s/azure-keyvault-integration.yaml
sed -i "s/<IDENTITY_CLIENT_ID>/$IDENTITY_CLIENT_ID/g" k8s/azure-keyvault-integration.yaml

# Apply
kubectl apply -f k8s/azure-keyvault-integration.yaml
```

### Step 7: Update Deployments to Use Secrets

See updated deployment files in `k8s/*-deployment-keyvault.yaml`

## Option 2: External Secrets Operator (Alternative)

### Install External Secrets Operator

```bash
helm repo add external-secrets https://charts.external-secrets.io
helm install external-secrets \
  external-secrets/external-secrets \
  -n external-secrets-system \
  --create-namespace
```

### Create SecretStore

```yaml
apiVersion: external-secrets.io/v1beta1
kind: SecretStore
metadata:
  name: azure-keyvault-store
  namespace: scraper-microservices
spec:
  provider:
    azurekv:
      authType: WorkloadIdentity
      vaultUrl: "https://<KEY_VAULT_NAME>.vault.azure.net"
      serviceAccountRef:
        name: scraper-sa
```

### Create ExternalSecret

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: scraper-secrets
  namespace: scraper-microservices
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: azure-keyvault-store
    kind: SecretStore
  target:
    name: database-secret
    creationPolicy: Owner
  data:
  - secretKey: DB_PASSWORD
    remoteRef:
      key: db-password
  - secretKey: API_KEY
    remoteRef:
      key: api-key
```

## Verification

```bash
# Check CSI driver pods
kubectl get pods -n kube-system -l app=secrets-store-csi-driver

# Check secret provider class
kubectl get secretproviderclass -n scraper-microservices

# Verify secrets are mounted
kubectl exec -it deployment/etl-service -n scraper-microservices -- ls -la /mnt/secrets-store/

# View secret values (for debugging only)
kubectl exec -it deployment/etl-service -n scraper-microservices -- cat /mnt/secrets-store/db-password
```

## Best Practices

1. **Never commit secrets to Git**
   - Use `.env` for local development only
   - Add `.env` to `.gitignore`
   - Use `.env.example` as template

2. **Rotate secrets regularly**
   ```bash
   az keyvault secret set --vault-name $KEY_VAULT_NAME --name db-password --value "new-password"
   # Restart pods to pick up new secrets
   kubectl rollout restart deployment/etl-service -n scraper-microservices
   ```

3. **Use separate Key Vaults per environment**
   - Development: `scraper-kv-dev`
   - Staging: `scraper-kv-staging`
   - Production: `scraper-kv-prod`

4. **Enable Key Vault audit logging**
   ```bash
   az monitor diagnostic-settings create \
     --name keyvault-audit \
     --resource $KEY_VAULT_ID \
     --logs '[{"category": "AuditEvent","enabled": true}]' \
     --workspace <LOG_ANALYTICS_WORKSPACE_ID>
   ```

5. **Use Managed Identities (no passwords)**
   - Workload Identity (recommended for AKS)
   - Pod Identity (legacy)
   - Service Principal (last resort)

## Troubleshooting

### Secrets not mounting
```bash
# Check CSI driver logs
kubectl logs -n kube-system -l app=secrets-store-csi-driver --tail=50

# Check provider logs
kubectl logs -n kube-system -l app=secrets-store-provider-azure --tail=50

# Describe pod
kubectl describe pod <pod-name> -n scraper-microservices
```

### Access denied errors
```bash
# Verify Key Vault permissions
az keyvault show --name $KEY_VAULT_NAME --query properties.accessPolicies

# Check managed identity
az identity show --name $IDENTITY_NAME --resource-group $RESOURCE_GROUP

# Verify federated credential
az identity federated-credential list \
  --identity-name $IDENTITY_NAME \
  --resource-group $RESOURCE_GROUP
```

## Environment-Specific Configuration

### Local Development (.env)
```bash
# Use .env file
cp .env.example .env
# Edit .env with local values
docker-compose up -d
```

### AKS Staging/Production (Azure Key Vault)
```bash
# Secrets come from Key Vault
# No .env file needed
kubectl apply -f k8s/
```

## Migration Checklist

- [ ] Create Azure Key Vault
- [ ] Enable CSI driver on AKS
- [ ] Create managed identity
- [ ] Store all secrets in Key Vault
- [ ] Configure Workload Identity
- [ ] Update Kubernetes manifests
- [ ] Test secret mounting
- [ ] Remove hardcoded secrets from manifests
- [ ] Update CI/CD pipeline
- [ ] Document secret rotation procedure
