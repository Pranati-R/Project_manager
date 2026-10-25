# Welcome

This guide helps you put a web project on the **Gateway**, so that you and your team can open it in a
browser at an address like `http://server:8280/myapp/`.

You do not need to know nginx. You do not need to be an expert. If you can start your project on your
own computer, you can do this.

## What is the gateway?

A **gateway** is one front door for many projects.

Without a gateway, every project needs its own port:

```
http://server:5173      -> shop
http://server:3000      -> blog
http://server:8000      -> notes API
```

You must remember the numbers. Every port is a new thing to open and protect.

With the gateway there is **one** port, and each project gets a **name** after it:

```
http://server:8280/shop/
http://server:8280/blog/
http://server:8280/notes/
```

Behind the door, your projects keep running as they always did. The gateway only forwards each visitor
to the right one.

> **Tip:** The part after the port (`/shop/`) is called the **path**. You choose it when you add a
> project.

## What do I get?

- One easy address for every project
- A dashboard to add, test and switch projects on and off
- Safe changes: every change is checked first, and a bad one never goes live
- Private access: only people on your network (Tailscale) can open your projects

## Who is this for?

Students and developers who build small web projects: a React or Vue frontend, a Python or Node
backend, or both. The pages are written step by step, and every technical word is explained in the
[Glossary](glossary.md).

## What you need before you start

- A project that runs on the server (you can start it and it listens on a port)
- A login for this dashboard
- About 10 minutes

## The one thing to remember

> **Note:** Your **frontend** has to be told where it lives (for example `/shop/`). Your **backend does
> not**. The gateway takes care of it. The next page explains why.

## Where to go next

1. [How it works](how-it-works.md): the idea in 5 minutes
2. [Quick start](quick-start.md): put your first project online
3. [Choose your project type](choose-type.md): the setup page for your kind of project
