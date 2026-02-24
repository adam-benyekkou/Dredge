import { defineConfig } from 'vitepress'

export default defineConfig({
  title: "Dredge",
  head: [['link', { rel: 'icon', href: '/Dredge/assets/dredge_logo.png' }]],
  description: "Docker FinOps & Lifecycle Management Tool",
  base: "/Dredge/",
  ignoreDeadLinks: [
    // Ignore all localhost links
    /^https?:\/\/localhost/,
  ],
  themeConfig: {
    logo: '/assets/dredge_logo.png',
    nav: [
      { text: 'Home', link: '/' },
      { text: 'Guide', link: '/guide/introduction' },
      { text: 'Reference', link: '/reference/api' }
    ],

    sidebar: [
      {
        text: 'Getting Started',
        items: [
          { text: 'Introduction', link: '/guide/introduction' },
          { text: 'Quick Start', link: '/guide/quick-start' },
          { text: 'Configuration', link: '/guide/configuration' },
        ]
      },
      {
        text: 'Core Concepts',
        items: [
          { text: 'Images Lifecycle', link: '/concepts/images' },
          { text: 'Volumes Management', link: '/concepts/volumes' },
          { text: 'Cleanup Policies', link: '/concepts/policies' },
          { text: 'Quarantine Management', link: '/concepts/quarantine' },
          { text: 'FinOps Metrics', link: '/concepts/finops' },
          { text: 'Architecture', link: '/concepts/architecture' },
        ]
      },
      {
        text: 'Registry Setup',
        items: [
          { text: 'Overview', link: '/registry/overview' },
          { text: 'Docker Hub', link: '/registry/docker-hub' },
          { text: 'AWS ECR', link: '/registry/aws-ecr' },
          { text: 'Google Artifact Registry', link: '/registry/gcp-gar' },
          { text: 'Azure Container Registry', link: '/registry/azure-acr' },
          { text: 'GitHub Container Registry', link: '/registry/ghcr' },
          { text: 'Custom Registries', link: '/registry/custom' },
        ]
      },
      {
        text: 'Deployment',
        items: [
          { text: 'Self-Hosting', link: '/deployment/self-hosting' },
          { text: 'Production Guide', link: '/deployment/production' },
        ]
      }
    ],

    socialLinks: [
      { icon: 'github', link: 'https://github.com/adam-benyekkou/Dredge' }
    ],
    
    footer: {
      message: 'Released under the MIT License.',
      copyright: 'Copyright © 2024-present Dredge Team'
    }
  }
})
