import DefaultTheme from 'vitepress/theme'
import { onMounted, watch, nextTick } from 'vue'
import { useRoute } from 'vitepress'
import './custom.css'

export default {
  extends: DefaultTheme,
  setup() {
    const route = useRoute()
    const initZoom = () => {
      if (typeof window === 'undefined') return
      
      const images = document.querySelectorAll('.vp-doc img')
      images.forEach((img) => {
        if (img.classList.contains('zoom-bound')) return
        img.classList.add('zoom-bound')
        img.style.cursor = 'zoom-in'
        
        img.addEventListener('click', (e) => {
          e.stopPropagation()
          const target = e.target as HTMLImageElement
          const src = target.src
          const alt = target.alt
          
          const overlay = document.createElement('div')
          overlay.className = 'zoom-overlay'
          overlay.onclick = () => overlay.remove()
          
          const zoomedImg = document.createElement('img')
          zoomedImg.src = src
          zoomedImg.alt = alt
          zoomedImg.className = 'zoomed-img'
          
          overlay.appendChild(zoomedImg)
          document.body.appendChild(overlay)
        })
      })
    }

    onMounted(() => {
      initZoom()
    })

    watch(
      () => route.path,
      () => nextTick(() => initZoom())
    )
  }
}
