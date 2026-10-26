<!-- A sample "Onboard an app" issue body, as GitHub renders the form; used by the parser test in CI. -->
### App name

sample

### GitHub repository

DEVOPS-CANARY/sample-app

### Backend

nestjs

### Backend port

3001

### Backend database layer

typeorm

### Frontend

nextjs

### Background worker (name)

notifier

### Worker command

node dist/worker.js

### Package manager

yarn

### The app needs

- [x] PostgreSQL
- [x] Redis
- [ ] Kafka

### Owner

@platform-team

### Readiness (platform plan §11)

- [x] Health endpoints for liveness and readiness (A3)
- [ ] All configuration from environment variables; optional variables really optional (A5)
