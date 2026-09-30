import express from "express";
const app=express();
app.get("/",(_req,res)=>res.json({ok:true,service:"GB YS Mail Bridge"}));
app.get("/health",(_req,res)=>res.json({ok:true}));
app.listen(process.env.PORT||3000);
