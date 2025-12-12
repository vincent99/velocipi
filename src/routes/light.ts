import {Router} from 'express'

const router = Router()

router.get("/", async (_, res) => {
  const ambient = await res.locals.light.getAmbientLux()
  const white = await res.locals.light.getWhiteLux()
  res.setHeader('Content-Type', 'application/json')

  res.end(JSON.stringify({
    ambient, white
  }, null, 2))
})

export default router


