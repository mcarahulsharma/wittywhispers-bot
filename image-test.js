(() => {
"use strict";
const API_BASE="https://generativelanguage.googleapis.com/v1/models/";
const form=document.getElementById("generatorForm"),apiKey=document.getElementById("apiKey"),model=document.getElementById("model"),aspectRatio=document.getElementById("aspectRatio"),prompt=document.getElementById("prompt"),generate=document.getElementById("generate"),clear=document.getElementById("clear"),toggleKey=document.getElementById("toggleKey"),status=document.getElementById("status"),result=document.getElementById("result"),output=document.getElementById("output"),download=document.getElementById("download");
let objectUrl=null;
function setStatus(message,kind){status.hidden=!message;status.textContent=message;status.className="status "+(kind||"")}
function clearImage(){if(objectUrl){URL.revokeObjectURL(objectUrl);objectUrl=null}output.removeAttribute("src");result.hidden=true}
function extractError(data){const message=data&&data.error&&data.error.message;if(!message)return"Google API returned an unexpected response.";return message.replace(/AIza[0-9A-Za-z_-]{20,}/g,"[redacted]")}
toggleKey.addEventListener("click",()=>{const visible=apiKey.type==="text";apiKey.type=visible?"password":"text";toggleKey.textContent=visible?"Show":"Hide"});
clear.addEventListener("click",()=>{form.reset();apiKey.value="";prompt.value="";clearImage();setStatus("")});
download.addEventListener("click",()=>{if(!objectUrl)return;const a=document.createElement("a");a.href=objectUrl;a.download="wittywhispers-generated.png";document.body.appendChild(a);a.click();a.remove()});
form.addEventListener("submit",async event=>{
event.preventDefault();clearImage();setStatus("");
const key=apiKey.value.trim(),text=prompt.value.trim();
if(!key){setStatus("Enter your Google API key.","error");return}
if(!text){setStatus("Enter an image prompt.","error");return}
generate.disabled=true;generate.textContent="Generating…";setStatus("Sending the prompt to Google Gemini…");
try{
const body={contents:[{parts:[{text:text}]}],generationConfig:{responseModalities:["IMAGE"],responseFormat:{image:{aspectRatio:aspectRatio.value}}}};
if(model.value==="gemini-3.1-flash-image")body.generationConfig.responseFormat.image.imageSize="1K";
const response=await fetch(API_BASE+encodeURIComponent(model.value)+":generateContent",{method:"POST",headers:{"Content-Type":"application/json","x-goog-api-key":key},body:JSON.stringify(body),cache:"no-store",credentials:"omit",referrerPolicy:"no-referrer"});
const data=await response.json().catch(()=>null);
if(!response.ok)throw new Error(extractError(data));
const parts=data&&data.candidates&&data.candidates[0]&&data.candidates[0].content&&data.candidates[0].content.parts||[];
const imagePart=parts.find(p=>p.inlineData&&p.inlineData.data&&p.inlineData.mimeType);
if(!imagePart){const textPart=parts.find(p=>p.text);throw new Error((textPart&&textPart.text)||"The API returned no image. Check the selected model, API access, and prompt.")}
const binary=atob(imagePart.inlineData.data),bytes=new Uint8Array(binary.length);
for(let i=0;i<binary.length;i++)bytes[i]=binary.charCodeAt(i);
objectUrl=URL.createObjectURL(new Blob([bytes],{type:imagePart.inlineData.mimeType}));
output.src=objectUrl;result.hidden=false;setStatus("Image generated successfully.","success");
}catch(error){setStatus(error instanceof Error?error.message:"Generation failed.","error")}
finally{generate.disabled=false;generate.textContent="Generate image"}
});
})();