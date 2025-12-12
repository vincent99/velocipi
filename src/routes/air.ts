import {Router} from 'express'

const router = Router()

router.get("/", async (_, res) => {
  const reading = await res.locals.air.read()
  res.setHeader('Content-Type', 'application/json')
  res.end(JSON.stringify(reading, null, 2))
})

export default router


