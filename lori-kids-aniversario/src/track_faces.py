import cv2, numpy as np, subprocess, json, sys
U,S=sys.argv[1],sys.argv[2]  # pasta dos originais, pasta de trabalho
files={'c1':'IMG_2310.mov','c2':'IMG_2311.mov','c3':'copy_1A2C98C5-868B-47EB-A77D-83533818926B.mov','c4':'IMG_2323.mov'}
cas=cv2.CascadeClassifier(cv2.data.haarcascades+'haarcascade_frontalface_default.xml')
W,H=540,960; out={}
for k,f in files.items():
    p=subprocess.Popen(['ffmpeg','-v','error','-i',f"{U}/{f}",'-vf',f'fps=30,scale={W}:{H}','-f','rawvideo','-pix_fmt','bgr24','-'],stdout=subprocess.PIPE)
    boxes=[];shirt=[];allm=[]
    while True:
        b=p.stdout.read(W*H*3)
        if len(b)<W*H*3: break
        im=np.frombuffer(b,np.uint8).reshape(H,W,3)
        g=cv2.cvtColor(im,cv2.COLOR_BGR2GRAY)
        fs=cas.detectMultiScale(g,1.1,5,minSize=(40,40))
        if len(fs):
            x,y,w,h=max(fs,key=lambda r:r[2]*r[3]); boxes.append([x/W,y/H,w/W,h/H])
            sy=int(y+h*1.9); sx=int(x+w*0.15); patch=im[sy:sy+int(h*0.5), sx:sx+int(w*0.7)]
            if patch.size: shirt.append(patch.reshape(-1,3).mean(0)[::-1])
        else: boxes.append(None)
        allm.append(im.reshape(-1,3).mean(0)[::-1])
    out[k]=boxes
    det=[b for b in boxes if b]; a=np.array(det)
    print(k,len(boxes),'det',len(det),'face cx %.2f cy %.2f w %.2f h %.2f'%tuple(a.mean(0)[[0,1,2,3]]+[a.mean(0)[2]/2,a.mean(0)[3]/2,0,0]),
      'cx range %.2f-%.2f cy %.2f-%.2f'%((a[:,0]+a[:,2]/2).min(),(a[:,0]+a[:,2]/2).max(),(a[:,1]+a[:,3]/2).min(),(a[:,1]+a[:,3]/2).max()),
      'shirtRGB',np.round(np.median(shirt,0)), 'frameRGB',np.round(np.mean(allm,0)))
json.dump(out,open(f"{S}/faces.json","w"))
