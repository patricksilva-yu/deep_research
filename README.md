# PR Structure
- Main branch will be used for deployment
- Develop branch will be used for merging our feat branches together
- Feat branches: have branches using 'feat/<feature_name>'

# Deployment
- Github Action of creating docker image of latest main branch
- Service TBD (Render, fly.io) will take the docker image and deploy it

