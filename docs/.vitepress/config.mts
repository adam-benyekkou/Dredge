import { defineConfig } from 'vitepress'

export default defineConfig({
  title: "Dredge",
  description: "Docker FinOps & Lifecycle Management Tool",
  themeConfig: {
    nav: [
      { text: 'Home', link: '/' },
      { text: 'Guide', link: '/guide/introduction' },
      { text: 'Reference', link: '/reference/api' }
    ],

    sidebar: [
      {
        text: 'Guide',
        items: [
          { text: 'Introduction', link: '/guide/introduction' },
          { text: 'Getting Started', link: '/guide/getting-started' },
          { text: 'Configuration', link: '/guide/configuration' },
        ]
      },
      {
        text: 'Registry Providers',
        items: [
          { text: 'Overview', link: '/registry/overview' },
          { text: 'Basic Auth (Tier 1)', link: '/registry/basic-auth' },
          { text: 'AWS ECR (Tier 3)', link: '/registry/aws-ecr' },
          { text: 'GCP Artifact Registry (Tier 3)', link: '/registry/gcp-gar' },
        ]
      },
      {
        text: 'Architecture',
        items: [
          { text: 'Design', link: '/architecture/design' },
          { text: 'Authentication', link: '/architecture/authentication' },
        ]
      }
    ],

    socialLinks: [
      { icon: 'github', link: 'https://github.com/adam-benyekkou/Dredge' }
    ]
  }
})
